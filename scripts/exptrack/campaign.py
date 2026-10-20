"""Tracked campaign runner: paired arms with a frozen selection, registered in
SQLite, MLflow mandatory.

    python scripts/run_hyperparameter_search.py snapshot --root runs/<id> --manifest scripts/campaigns/<id>.json
    PYTHONPATH=runs/<id>/snapshot/src:runs/<id>/snapshot/scripts .venv/bin/python -m exptrack \\
        campaign run --root runs/<id> --db experiments.sqlite3

The manifest's "experiment" block is a complete experiment configuration
(schema.EXPERIMENT_SCHEMA). Before anything trains, the runner registers the
game version (hashed from the snapshot), the experiment, an immutable revision
and every run with its complete effective configuration, and refuses to start
unless MLflow answers. For each training job it then:

1. creates the MLflow run (tags exptrack.*, campaign, arm, seed, game) and a
   run_attempts row holding its id (reciprocal links), mirrors the run and
   experiment parameters into it;
2. materialises the configuration from the SQLite rows, checks its hash, and
   launches the snapshot's trainer with --mlflow-run-id;
3. checks the exit code, the summary and that the trainer parsed exactly the
   registered configuration; records artifacts;
4. runs the development evaluations (all protocol settings explicit, checked
   against what the evaluator reports), records them in SQLite and MLflow.

When every training job is done, the best non-reference arm is chosen on the
development bank by the registered rule and frozen (selection.json, with all
checkpoint hashes) before the final bank is opened for that arm and the
reference. results.json then applies the acceptance rule. Budget: every job's
full reservation is checked against the aggregate cap and the hard cutoff
before dispatch; actual elapsed single-thread time is recorded per part. One
infrastructure retry per job at most, never a performance-based one. An
exclusive lock prevents a second runner.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import db, schema, store
from .mlflow_sink import client_for, ensure_experiment, find_run_by_tag, log_params, preflight

THREADS = {k: "1" for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
PREFLIGHT_RESERVE_SECONDS = 600  # campaign preflight allowance, counted against the cap
RUNNER_FILE = "scripts/exptrack/campaign.py"  # the only file a recorded runner snapshot may change
# Development tie-breaks a manifest may state (ranking.tiebreak), applied in its order after the
# primary key (mean development clears, descending). Anything else is refused, never ignored.
TIEBREAKS = {
    "minimum training-seed completed fraction descending": lambda t: -t["min_seed_fraction"],
    "mean levels cleared at least once on the development bank": lambda t: -t["mean_levels_cleared"],
    "smaller parameter count": lambda t: t["parameter_count"],
    "arm id": None, "arm id ascending": None,
}


def iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)


class SystemicError(RuntimeError):
    """A correctness failure that must stop the campaign (not retried)."""


def rank_candidates(table: dict, candidates: list[str], tiebreak: list[str]) -> list[str]:
    """Mean development clears descending, then the manifest's tie-breaks in
    order, then arm id (always last, so the order is total)."""
    breaks = [TIEBREAKS[t] for t in tiebreak if TIEBREAKS[t] is not None]
    return sorted(candidates, key=lambda a: (-table[a]["mean_cleared"], *[f(table[a]) for f in breaks], a))


def process_start(pid: int) -> str | None:
    """The process's start time as ps reports it (None if it is not running);
    with the pid it identifies one process, since pids are reused."""
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return out or None


def live_processes_mentioning(path: Path) -> list[int]:
    """Pids of running processes with a command-line argument that is `path`
    (a run directory) or a file under it: the fallback identity when no child
    was recorded. Whole-token matching, so runs/x/a_s1 does not match a_s1_a2."""
    p = str(path).rstrip("/")
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if int(pid) != os.getpid() and any(t == p or t.startswith(p + "/") for t in cmd.split()):
            pids.append(int(pid))
    return pids


class Campaign:
    def __init__(self, root, db_path, require_snapshot_code: bool = True):
        self.root = Path(root).resolve()
        self.snap = self.root / "snapshot"
        self.info = json.loads((self.root / "snapshot.json").read_text())
        changed = [r for r, h in self.info["files"].items() if db.sha256_file(self.snap / r) != h]
        if changed:
            raise SystemExit(f"snapshot changed since it was frozen: {changed[:5]}")
        self.runner_snapshot = None
        here = Path(__file__).resolve()
        if require_snapshot_code and not here.is_relative_to(self.snap.resolve()):
            self.runner_snapshot = self._verify_runner_snapshot(here)
        mpath = self.snap / self.info["manifest"]
        if db.sha256_file(mpath) != self.info["manifest_sha256"]:
            raise SystemExit("manifest hash differs from snapshot.json")
        self.manifest = json.loads(mpath.read_text())
        self.cfg = schema.validate_experiment(self.manifest["experiment"])
        c = self.cfg
        if c["design.type"] not in ("paired_arms_with_selection", "search_batch"):
            raise SystemExit(f"this runner implements paired_arms_with_selection and search_batch, not "
                             f"{c['design.type']}")
        self.search_only = c["design.type"] == "search_batch"
        unknown = [t for t in c["ranking.tiebreak"] if t not in TIEBREAKS]
        if unknown:
            raise SystemExit(f"ranking.tiebreak {unknown} is not implemented by this runner; refusing to guess")
        if self.search_only and set(c["evaluation.seed_banks"]) != {"development"}:
            raise SystemExit("a search batch has a development bank only (no final bank)")
        if not c["tracking.required"] or not c["tracking.mlflow_uri"] or not c["tracking.mlflow_experiment"]:
            raise SystemExit("MLflow tracking is mandatory: tracking.required, mlflow_uri and mlflow_experiment")
        if c["evaluation.cap_frames"] != c["evaluation.max_steps"] * c["evaluation.frame_skip"]:
            raise SystemExit("evaluation.cap_frames != max_steps * frame_skip")
        self.db_path = Path(db_path).resolve()
        self.uri = c["tracking.mlflow_uri"]
        self.python = self.info["interpreter"]
        self.env = {**os.environ, **THREADS, "PYTHONPATH": f"{self.snap / 'src'}:{self.snap / 'scripts'}",
                    "PYTHONDONTWRITEBYTECODE": "1", "MLFLOW_TRACKING_URI": self.uri,
                    "MLFLOW_DISABLE_TELEMETRY": "true", "MLFLOW_DISABLE_AGENT_HINT": "1"}
        self.cutoff = dt.datetime.fromisoformat(c["budget.hard_cutoff"]) if c["budget.hard_cutoff"] else None
        self.cap_seconds = c["budget.aggregate_core_hours"] * 3600
        self.eval_hard = c["budget.per_evaluation_hard_seconds"]
        self.grace = c["budget.save_grace_seconds"]
        self.lock = threading.Lock()
        self.halted: str | None = None  # set by a systemic error: nothing new is dispatched
        self._local = threading.local()
        self.status_path = self.root / "status.json"
        self.status = json.loads(self.status_path.read_text()) if self.status_path.exists() else None

    def _verify_runner_snapshot(self, here: Path) -> str:
        """A corrected runner for a campaign whose frozen snapshot has a runner
        defect: a copy of the snapshot in which only RUNNER_FILE differs,
        recorded (with every file hash and the reason) in runner_snapshots.json.
        Training and evaluation still run from the original snapshot."""
        rec_path = self.root / "runner_snapshots.json"
        recs = json.loads(rec_path.read_text()) if rec_path.exists() else {}
        for name, rec in recs.items():
            d = (self.root / name).resolve()
            if not here.is_relative_to(d):
                continue
            files = {str(p.relative_to(d)): db.sha256_file(p) for p in sorted(d.rglob("*")) if p.is_file()}
            if files != rec["files"]:
                raise SystemExit(f"runner snapshot {name} changed since it was recorded")
            differ = {k for k in set(files) | set(self.info["files"]) if files.get(k) != self.info["files"].get(k)}
            if differ != {RUNNER_FILE}:
                raise SystemExit(f"runner snapshot {name} differs from the frozen snapshot in {sorted(differ)[:5]}")
            return name
        raise SystemExit(f"run me from the snapshot ({self.snap}) or a recorded runner snapshot, not {here}")

    # ------------------------------------------------------------ plumbing
    def con(self):
        if not hasattr(self._local, "con"):
            self._local.con = db.connect(self.db_path)
        return self._local.con

    def log(self, msg: str) -> None:
        line = f"{iso()} {msg}"
        print(line, flush=True)
        with self.lock, open(self.root / "events.log", "a") as f:
            f.write(line + "\n")

    def save(self) -> None:
        self.status["updated"] = iso()
        write_json_atomic(self.status_path, self.status)

    def acquire_runner_lock(self):
        self._lock_file = open(self.root / "runner.lock", "a+")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another runner holds runner.lock; refusing to start a duplicate")
        self._lock_file.seek(0)
        self._lock_file.truncate()
        self._lock_file.write(f"{os.getpid()} {iso()}\n")
        self._lock_file.flush()

    # -------------------------------------------------------- registration
    def register(self) -> dict:
        """Idempotent: the game version, experiment, revision and every run."""
        c, con = self.cfg, self.con()
        ref = c["design.reference_arm"]  # a search batch without the reference arm checks the shared settings
        ref_cfg = schema.validate_trainer_config({**c["shared.training"], **(c["design.arms"][ref] if ref else {})})
        if db.sha256_text(db.canonical(ref_cfg)) != c["reference.config_sha256"]:
            raise SystemicError("reference.config_sha256 does not match the reference arm's configuration")
        gid = store.register_game_version(con, c["game.name"], self.snap / "src" / "bubblebobblerl",
                                          c["game.source_commit"], self.manifest["game_description"])
        eid = store.register_experiment(con, self.manifest["campaign_id"], c["experiment.question"])
        rid = store.register_revision(con, eid, c, gid, self.manifest["change_note"])
        runs = {}
        for phase in c["design.phases"]:
            for seed in c["seeds.training"][phase]:
                for arm in self.arm_order():
                    runs[self.job_id(arm, seed)] = store.register_run(con, rid, arm, seed, phase=phase)
        return {"game_version_id": gid, "experiment_id": eid, "revision_id": rid, "runs": runs}

    def arm_order(self) -> list[str]:
        order = self.cfg["search.order"] or list(self.cfg["design.arms"])
        if sorted(order) != sorted(self.cfg["design.arms"]):
            raise SystemicError("search.order must list every arm exactly once")
        return order

    @staticmethod
    def job_id(arm: str, seed: int) -> str:
        return f"{arm}_s{seed}"

    def jobs(self) -> list[tuple[str, str, int]]:
        c = self.cfg
        return [(phase, arm, seed) for phase in c["design.phases"] for seed in c["seeds.training"][phase]
                for arm in self.arm_order()]

    # -------------------------------------------------------------- budget
    def train_reservation(self, phase: str) -> float:
        n_dev = len(self.cfg["evaluation.seed_banks"]["development"])
        return self.cfg["budget.per_run_wall_minutes"][phase] * 60 + self.grace + self.eval_hard * n_dev

    def final_reservation(self) -> float:
        if self.search_only:
            return 0.0
        return 2 * len(self.cfg["seeds.training"][self.cfg["design.phases"][0]]) * \
            len(self.cfg["evaluation.seed_banks"]["final"]) * self.eval_hard

    def spent(self) -> float:
        return sum(p.get("elapsed_seconds", 0.0) for p in self.status["parts"].values())

    def committed(self) -> float:
        """Allocated time so far plus the unspent part of every outstanding
        reservation: a queued job counts in full; a running or evaluating job
        counts its reservation minus what its current attempt has already used
        (that part is in spent()); the final bank likewise. Before 2026-10-19
        22:30 a job that had finished training but was still evaluating was
        counted twice (spent plus its full reservation), which refused
        capacity-1020's second wave."""
        total = self.spent()
        for phase, arm, seed in self.jobs():
            j = self.status["jobs"][self.job_id(arm, seed)]
            if j["state"] in ("done", "failed", "not_run"):
                continue
            used = 0.0
            if j["state"] in ("running", "evaluating") and j.get("attempt_id"):
                used = sum(p.get("elapsed_seconds", 0.0) for k, p in self.status["parts"].items()
                           if k.startswith(j["attempt_id"] + "/"))
            total += max(0.0, self.train_reservation(phase) - used)
        if self.status.get("final_state") != "done":
            used = sum(p.get("elapsed_seconds", 0.0) for k, p in self.status["parts"].items() if "/eval/final/" in k)
            total += max(0.0, self.final_reservation() - used)
        total += sum(self.status.get("retry_reservations", {}).values())  # evaluation retries in flight
        return total

    def fits(self, seconds: float, committed: float) -> str | None:
        """None if a part needing `seconds` fits the deadline and the total
        `committed` (from committed(), which already includes that part) fits
        the cap; a reason otherwise."""
        if self.cutoff and dt.datetime.now().astimezone() + dt.timedelta(seconds=seconds) > self.cutoff:
            return "its full reservation would end after the hard cutoff"
        if committed > self.cap_seconds:
            return "the aggregate core-hour cap would be exceeded"
        return None

    # ----------------------------------------------------------------- run
    def run(self) -> None:
        self.acquire_runner_lock()
        preflight(self.uri)
        ids = self.register()
        c = self.cfg
        if self.status is None:
            self.status = {"campaign": self.manifest["campaign_id"], "snapshot_commit": self.info["commit"],
                           "manifest_sha256": self.info["manifest_sha256"], "created": iso(),
                           "db": str(self.db_path), "mlflow_tracking_uri": self.uri, **ids,
                           "jobs": {}, "parts": {}, "final_state": "pending"}
        for phase, arm, seed in self.jobs():
            self.status["jobs"].setdefault(self.job_id(arm, seed), {
                "phase": phase, "arm": arm, "seed": seed, "state": "queued",
                "run_id": ids["runs"][self.job_id(arm, seed)], "attempts": 0})
        for jid, j in self.status["jobs"].items():  # never dispatched: reconsidered under current accounting
            if j["state"] == "not_run" and j["attempts"] == 0:
                store.add_event(self.con(), "requeued", {"previous_reason": j.get("error")}, run_id=j["run_id"])
                j.update(state="queued", requeued_from=j.pop("error", None))
        self.reconcile_all()
        total = self.committed()
        if total > self.cap_seconds:
            raise SystemExit(f"plan needs {total / 3600:.2f} reserved core-hours, cap "
                             f"{c['budget.aggregate_core_hours']}")
        con = self.con()
        if self.runner_snapshot:
            self.status.setdefault("runner_snapshots", [])
            if self.runner_snapshot not in self.status["runner_snapshots"]:
                self.status["runner_snapshots"].append(self.runner_snapshot)
            self.save()
        store.add_event(con, "campaign_run_started", {"pid": os.getpid(), "reserved_core_hours": total / 3600,
                                                      "runner_snapshot": self.runner_snapshot},
                        experiment_id=ids["experiment_id"], revision_id=ids["revision_id"])
        self.log(f"{self.manifest['campaign_id']} start; snapshot {self.info['commit'][:10]}; "
                 f"{len(self.jobs())} training jobs; plan {total / 3600:.2f} of {c['budget.aggregate_core_hours']} "
                 f"core-hours; pid {os.getpid()}")
        with ThreadPoolExecutor(c["budget.max_concurrent_jobs"]) as pool:
            for f in [pool.submit(self.train_job, *j) for j in self.jobs()]:
                f.result()
        states = {k: j["state"] for k, j in self.status["jobs"].items()}
        if any(s != "done" for s in states.values()):
            self.log(f"training incomplete {states}; no selection, no final bank opened")
            store.add_event(con, "campaign_incomplete", {"states": states}, experiment_id=ids["experiment_id"],
                            revision_id=ids["revision_id"])
            return
        if self.search_only:
            self.batch_results()
            return
        self.select_and_finalize()

    def batch_results(self) -> dict:
        """A search-only batch: every job's development results, absolute, with
        no selection and no final bank (ranking happens across the program)."""
        c, con = self.cfg, self.con()
        out = {"campaign": self.manifest["campaign_id"], "experiment_id": self.status["experiment_id"],
               "revision_id": self.status["revision_id"], "search_only": True,
               "development_bank": c["evaluation.seed_banks"]["development"], "arms": {}, "written": iso()}
        for arm in self.arm_order():
            runs = {}
            for s in c["seeds.training"][c["design.phases"][0]]:
                j = self.status["jobs"][self.job_id(arm, s)]
                evals = {}
                for r in con.execute("SELECT protocol_json, results_json FROM evaluations WHERE run_id = ? AND role = "
                                     "'development' AND checkpoint_sha256 = ?", (j["run_id"], j["model_sha256"])):
                    res = json.loads(r["results_json"])
                    evals[str(json.loads(r["protocol_json"])["seed"])] = {
                        k: res[k] for k in ("cleared", "died", "timeout", "episodes", "levels_cleared")}
                cleared = sum(e["cleared"] for e in evals.values())
                episodes = sum(e["episodes"] for e in evals.values())
                runs[str(s)] = {"run_id": j["run_id"], "mlflow_run_id": j["mlflow_run_id"],
                                "model_sha256": j["model_sha256"], "steps": j["steps"], "updates": j["updates"],
                                "train_seconds": j.get("train_seconds"), "development": evals,
                                "cleared": cleared, "episodes": episodes,
                                "fraction": cleared / episodes if episodes else None}
            tot_c = sum(r["cleared"] for r in runs.values())
            tot_e = sum(r["episodes"] for r in runs.values())
            out["arms"][arm] = {"overrides": c["design.arms"][arm], "runs": runs, "cleared": tot_c, "episodes": tot_e,
                                "fraction": tot_c / tot_e if tot_e else None,
                                "min_seed_fraction": min(r["fraction"] for r in runs.values())}
        out["allocated_core_hours"] = self.spent() / 3600
        path = self.root / "batch_results.json"
        write_json_atomic(path, out)
        store.add_artifact(con, "batch_results", path, db.sha256_file(path), experiment_id=self.status["experiment_id"])
        store.add_event(con, "search_batch_complete", {a: {k: v[k] for k in ("cleared", "episodes", "fraction")}
                                                       for a, v in out["arms"].items()},
                        experiment_id=self.status["experiment_id"], revision_id=self.status["revision_id"])
        self.log("search batch complete: " + "; ".join(f"{a} {v['cleared']}/{v['episodes']}" for a, v in
                                                       out["arms"].items()) + f"; allocated "
                 f"{out['allocated_core_hours']:.2f} core-hours (no selection, no final bank)")
        return out

    def reconcile_all(self) -> None:
        """After a previous runner stopped: reconcile every job (running or
        evaluating ones fully; any other job's leftover child identity, such as
        a final-bank evaluator on a done job), then drop retry reservations,
        whose children have just been reconciled."""
        for jid, j in self.status["jobs"].items():
            if j["state"] in ("running", "evaluating"):
                self.reconcile(jid, j)
            else:
                self.reconcile_stray_child(jid, j)
        stale = self.status.pop("retry_reservations", {})
        if stale:
            store.add_event(self.con(), "retry_reservations_released", {"keys": sorted(stale)},
                            experiment_id=self.status.get("experiment_id"))
        self.save()

    def live_children(self, j: dict) -> list[int]:
        """Live processes belonging to this job: its recorded child (same pid and
        start time) or any process naming its run directory."""
        child, alive = j.get("child"), []
        if child and child.get("start") and process_start(child["pid"]) == child["start"]:
            alive.append(child["pid"])
        if j.get("dir"):
            alive += [p for p in live_processes_mentioning(Path(j["dir"])) if p not in alive]
        return alive

    def charge_dead_child(self, j: dict) -> None:
        """A recorded child that is gone without its cost recorded: charge from
        its recorded start (capped at its allowance) and clear the record."""
        child = j.pop("child", None)
        if not child:
            return
        cap = self.train_reservation(j["phase"]) if child["kind"] == "train" else self.eval_hard
        charged = round(min(max(0.0, time.time() - child["since"]), cap), 1)
        self.status["parts"][f"{j.get('attempt_id')}/{child['kind']}/interrupted-{int(child['since'])}"] = {
            "elapsed_seconds": charged, "estimated": "from the recorded child start; the child is gone"}

    def reconcile_stray_child(self, jid: str, j: dict) -> None:
        """A job that is not running or evaluating but may still own a process
        (e.g. a final-bank evaluator on a done job). A live one blocks final
        dispatch (orphan_child); a dead one is charged and cleared. Training
        state and the frozen selection are left alone."""
        alive = self.live_children(j) if (j.get("child") or j.get("dir")) else []
        if alive:
            j["orphan_child"] = {"pids": alive, "child": j.get("child")}
            store.add_event(self.con(), "orphan_detected", {"pids": alive, "child": j.get("child"),
                                                            "state": j["state"]},
                            run_id=j["run_id"], attempt_id=j.get("attempt_id"))
            self.log(f"ORPHAN {jid}: live processes {alive} from a previous runner; final dispatch blocked")
        else:
            self.charge_dead_child(j)
            j.pop("orphan_child", None)

    def reconcile(self, jid: str, j: dict) -> None:
        """A job a previous runner left running or evaluating. A child that is
        still alive (recorded pid and start time, or any process naming the run
        directory) makes the job "orphaned": it is not dispatched again and its
        full reservation stays committed until someone reviews it. A dead
        child's elapsed time, never recorded, is charged from its recorded start.
        A job that was evaluating a verified endpoint resumes evaluation instead
        of retraining; otherwise the attempt counts as an infrastructure failure."""
        con = self.con()
        child = j.get("child")
        alive = self.live_children(j)
        if alive:
            j.update(state="orphaned", error=f"processes {alive} from a previous runner are still alive; "
                                             "not dispatched again")
            store.add_event(con, "orphan_detected", {"pids": alive, "child": child}, run_id=j["run_id"],
                            attempt_id=j.get("attempt_id"))
            self.log(f"ORPHAN {jid}: live processes {alive}; not dispatched again, reservation kept")
            return
        if child:
            self.charge_dead_child(j)
        elif j["state"] == "running" and j.get("attempt_id"):
            launched = con.execute("SELECT 1 FROM events WHERE attempt_id = ? AND event = 'training_started'",
                                   (j["attempt_id"],)).fetchone()
            if launched and f"{j['attempt_id']}/train" not in self.status["parts"]:
                j.update(state="needs_review", error="training was launched but neither its process record nor "
                                                     "its cost survived: cost unknowable, not retried automatically")
                store.add_event(con, "needs_review", {"reason": j["error"]}, run_id=j["run_id"],
                                attempt_id=j["attempt_id"])
                self.log(f"NEEDS REVIEW {jid}: {j['error']}")
                return
        model = Path(j["dir"]) / "model.pt" if j.get("dir") else None
        if (j["state"] == "evaluating" and j.get("model_sha256") and model and model.exists()
                and db.sha256_file(model) == j["model_sha256"]):
            j["resume_evaluation"] = True
            store.add_event(con, "evaluation_resumed", {"model_sha256": j["model_sha256"]}, run_id=j["run_id"],
                            attempt_id=j.get("attempt_id"))
            return
        j.update(state="queued", retryable=True, error="runner stopped during this attempt")
        store.add_event(con, "failed", {"stage": "runner stopped", "infrastructure": True},
                        run_id=j["run_id"], attempt_id=j.get("attempt_id"))

    def run_child(self, j: dict | None, kind: str, argv: list[str], out: Path, err: Path, timeout: float,
                  cost_key: str):
        """Run one trainer or evaluator. Its identity is written to status.json
        before waiting, so a restarted runner can recognise it; when it ends,
        its elapsed time (parts[cost_key]) and the clearing of its identity are
        one status write, so a crash can never lose both. Returns (rc, seconds)."""
        t0 = time.time()
        with open(out, "w") as o, open(err, "w") as e:
            proc = subprocess.Popen(argv, env=self.env, stdout=o, stderr=e)
            if j is not None:
                with self.lock:
                    j["child"] = {"pid": proc.pid, "start": process_start(proc.pid), "kind": kind, "since": t0}
                    self.save()
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                rc = "timeout"
        seconds = round(time.time() - t0, 1)
        with self.lock:
            self.status["parts"][cost_key] = {"elapsed_seconds": seconds}
            if j is not None:
                j.pop("child", None)
            self.save()
        return rc, seconds

    def train_job(self, phase: str, arm: str, seed: int) -> None:
        jid = self.job_id(arm, seed)
        j = self.status["jobs"][jid]
        try:
            if j["state"] in ("orphaned", "needs_review"):
                return
            if j["state"] == "evaluating" and j.get("resume_evaluation"):
                self.dev_evaluations(phase, arm, seed, j)
            while j["state"] not in ("done", "failed", "orphaned", "needs_review"):
                if j["attempts"] >= 2 or (j["attempts"] == 1 and not j.get("retryable")):
                    with self.lock:
                        j["state"] = "failed"
                        self.save()
                    return
                with self.lock:
                    reason = self.halted or self.fits(self.train_reservation(phase), self.committed())
                    if reason:
                        j.update(state="not_run", error=reason)
                        self.save()
                if reason:
                    self.log(f"not run {jid}: {reason}")
                    store.add_event(self.con(), "not_run", {"reason": reason}, run_id=j["run_id"])
                    return
                self.attempt(phase, arm, seed, j)
        except SystemicError as e:
            with self.lock:
                self.halted = f"campaign halted by a systemic error in {jid}"
                j.update(state="failed", error=f"systemic: {e}", retryable=False)
                self.save()
            self.log(f"SYSTEMIC {jid}: {e}")
            raise

    def mlflow_run_for(self, run_id: str, attempt_n: int, phase: str, arm: str, seed: int):
        """The attempt's MLflow run: found by tag if an earlier dispatch created
        it (idempotent), otherwise created with parameters mirrored."""
        con, c = self.con(), self.cfg
        attempt_id = f"{run_id}-a{attempt_n}"
        client = client_for(self.uri)
        exp_id = ensure_experiment(client, c["tracking.mlflow_experiment"])
        found = find_run_by_tag(client, exp_id, "exptrack.attempt_id", attempt_id)
        if found:
            return client, exp_id, found.info.run_id, attempt_id
        rev = con.execute("SELECT experiment_id, revision_id FROM runs r JOIN experiment_revisions v "
                          "ON v.id = r.revision_id WHERE r.id = ?", (run_id,)).fetchone()
        run_key = con.execute("SELECT run_key FROM runs WHERE id = ?", (run_id,)).fetchone()["run_key"]
        tags = {"exptrack.db": str(self.db_path), "exptrack.experiment_id": rev["experiment_id"],
                "exptrack.revision_id": rev["revision_id"], "exptrack.run_id": run_id,
                "exptrack.run_key": run_key, "exptrack.attempt": str(attempt_n), "exptrack.attempt_id": attempt_id,
                "campaign": self.manifest["campaign_id"], "phase": phase, "arm": arm, "training_seed": str(seed),
                "game_version": c["game.name"], "game_source_hash": c["game.source_hash"],
                "snapshot_commit": self.info["commit"], "origin": "registered"}
        run = client.create_run(exp_id, run_name=f"{self.job_id(arm, seed)}-a{attempt_n}", tags=tags)
        params = {r["key"]: json.loads(r["value_json"]) for r in con.execute(
            "SELECT key, value_json FROM run_params WHERE run_id = ?", (run_id,))}
        params.update({f"experiment.{k}": v for k, v in c.items() if k != "shared.training"})
        for k, v in list(params.items()):  # MLflow caps a parameter value at 6000 characters
            text = v if isinstance(v, str) else json.dumps(v)
            if len(text) > 5000:
                params[k] = text[:4800] + f" ...[truncated; sha256 {db.sha256_text(text)[:16]}; full value in SQLite]"
        log_params(client, run.info.run_id, params)
        return client, exp_id, run.info.run_id, attempt_id

    def attempt(self, phase: str, arm: str, seed: int, j: dict) -> None:
        con, c = self.con(), self.cfg
        jid, run_id = self.job_id(arm, seed), j["run_id"]
        n = con.execute("SELECT COALESCE(MAX(attempt), 0) + 1 FROM run_attempts WHERE run_id = ?",
                        (run_id,)).fetchone()[0]
        d = self.root / jid if n == 1 else self.root / f"{jid}_a{n}"
        d.mkdir(exist_ok=True)
        preflight(self.uri)
        client, exp_id, ml_run, attempt_id = self.mlflow_run_for(run_id, n, phase, arm, seed)
        existing = store.find_attempt(con, run_id, n)
        if existing is None:
            store.create_attempt(con, run_id, str(d), self.uri, exp_id, ml_run)
        elif existing["mlflow_run_id"] != ml_run:
            raise SystemicError(f"{attempt_id}: SQLite and MLflow disagree on the run id")
        with self.lock:
            j.update(state="running", attempts=n, dir=str(d), mlflow_run_id=ml_run, attempt_id=attempt_id,
                     started=iso(), retryable=False)
            j.pop("error", None)
            self.save()
        # The configuration the trainer gets is rebuilt from the SQLite rows and
        # checked against the registered hash.
        eff = store.reconstruct_run_config(con, run_id)
        cfg_path = d / "run_config.json"
        cfg_path.write_text(json.dumps(eff, indent=1))
        registered = con.execute("SELECT config_sha256 FROM runs WHERE id = ?", (run_id,)).fetchone()[0]
        if db.sha256_text(db.canonical(json.loads(cfg_path.read_text()))) != registered:
            raise SystemicError(f"{jid}: materialised configuration does not match the registered hash")
        t0 = time.time()
        argv = [self.python, str(self.snap / "scripts" / "train_ppo.py"), "--config", str(cfg_path),
                "--run-dir", str(d), "--run-name", f"{jid}-a{n}", "--wall-start", repr(t0),
                "--mlflow-tracking-uri", self.uri, "--mlflow-run-id", ml_run,
                "--metric-outbox", str(d / "mlflow_outbox.jsonl"), "--log-every", "5", "--no-tensorboard",
                "--quiet"]
        (d / "argv.json").write_text(json.dumps(argv))
        store.add_event(con, "training_started", {"argv": argv, "mlflow_run_id": ml_run}, run_id=run_id,
                        attempt_id=attempt_id)
        self.log(f"start {jid} attempt {n} (mlflow {ml_run[:8]})")
        timeout = eff["wall_minutes"] * 60 + self.grace
        rc, train_seconds = self.run_child(j, "train", argv, d / "train.out", d / "train.err", timeout,
                                           f"{attempt_id}/train")
        summary_path = d / "train_summary.json"
        if rc != 0 or not summary_path.exists() or not (d / "model.pt").exists():
            err = (d / "train.err").read_text()[-600:]
            infra = rc == "timeout" or "TrackingUnavailable" in err or rc in (-9, -15, 137)
            store.add_event(con, "failed", {"stage": "training", "rc": rc, "stderr_tail": err,
                                            "infrastructure": infra}, run_id=run_id, attempt_id=attempt_id)
            with self.lock:
                j.update(state="queued" if infra else "failed", error=f"training exit {rc}", retryable=infra)
                self.save()
            self.log(f"FAILED {jid} attempt {n}: training exit {rc} ({'infrastructure' if infra else 'not retried'})")
            return
        trained = json.loads((d / "config.json").read_text())
        drift = {k: (trained.get(k), v) for k, v in eff.items() if trained.get(k) != v}
        if drift:
            raise SystemicError(f"{jid}: trainer ran a different configuration {drift}")
        summary = json.loads(summary_path.read_text())
        model_sha = db.sha256_file(d / "model.pt")
        for kind, name in (("checkpoint", "model.pt"), ("optimizer", "optimizer.pt"), ("trainer_config", "config.json"),
                           ("architecture", "arch.json"), ("train_summary", "train_summary.json"),
                           ("mlflow_status", "mlflow_status.json"), ("metric_outbox", "mlflow_outbox.jsonl")):
            if (d / name).exists():
                store.add_artifact(con, kind, d / name, db.sha256_file(d / name), run_id=run_id,
                                   attempt_id=attempt_id)
        store.add_event(con, "training_finished", {"summary": summary, "model_sha256": model_sha,
                                                   "elapsed_seconds": train_seconds},
                        run_id=run_id, attempt_id=attempt_id)
        with self.lock:
            j.update(state="evaluating", model_sha256=model_sha, steps=summary["steps"], updates=summary["updates"],
                     train_seconds=train_seconds)
            self.save()
        self.dev_evaluations(phase, arm, seed, j)

    def dev_evaluations(self, phase: str, arm: str, seed: int, j: dict) -> None:
        """The development bank on the job's verified endpoint. An evaluation
        that fails (after its one retry) fails the job; the trained endpoint is
        never discarded and retrained because an evaluation failed."""
        con, c = self.con(), self.cfg
        jid, run_id, d = self.job_id(arm, seed), j["run_id"], Path(j["dir"])
        if db.sha256_file(d / "model.pt") != j["model_sha256"]:
            raise SystemicError(f"{jid}: endpoint changed after training")
        eff = store.reconstruct_run_config(con, run_id)
        dev = {}
        for s in c["evaluation.seed_banks"]["development"]:
            dev[s] = self.evaluate_with_retry(j, "development", s, eff, d / f"eval_development_{s}.json")
            if dev[s] is None:
                with self.lock:
                    j.update(state="failed", error=f"development evaluation {s} failed twice", retryable=False)
                    self.save()
                self.log(f"FAILED {jid}: development evaluation {s} failed twice (endpoint kept)")
                return
        store.add_event(con, "finished", {"development": {s: r["cleared"] for s, r in dev.items()}},
                        run_id=run_id, attempt_id=j["attempt_id"])
        with self.lock:
            j.update(state="done", finished=iso(), development={str(s): r["cleared"] for s, r in dev.items()})
            j.pop("resume_evaluation", None)
            self.save()
        self.log(f"done {jid}: {j['steps']:,} steps; development clears "
                 f"{', '.join(str(r['cleared']) for r in dev.values())}")

    def evaluate_with_retry(self, j: dict, role: str, seed: int, eff: dict, out: Path) -> dict | None:
        """At most two tries. A retry goes beyond the job's reservation, so it
        is checked against the remaining budget and the deadline first; each
        try keeps its own output files and elapsed-time record."""
        for n in (1, 2):
            rkey = f"{j['attempt_id']}/eval/{role}/{seed}/try{n}"
            if n > 1:
                with self.lock:  # check and reserve in one step, so concurrent retries cannot share the room
                    reason = self.halted or self.fits(self.eval_hard, self.committed() + self.eval_hard)
                    if not reason:
                        self.status.setdefault("retry_reservations", {})[rkey] = self.eval_hard
                        self.save()
                if reason:
                    self.log(f"evaluation retry {role} {seed} for {j['attempt_id']} not run: {reason}")
                    return None
            target = out if n == 1 else out.with_name(f"{out.stem}.try{n}{out.suffix}")
            try:
                r = self.evaluate(j["run_id"], j["attempt_id"], j["mlflow_run_id"], Path(j["dir"]) / "model.pt",
                                  j["model_sha256"], eff, role, seed, target, j["steps"], try_n=n, job=j)
            finally:
                if n > 1:
                    with self.lock:  # its actual time is now in parts[...]; release the reservation
                        self.status.get("retry_reservations", {}).pop(rkey, None)
                        self.save()
            if r is not None:
                return r
        return None

    # ---------------------------------------------------------- evaluation
    def protocol(self, eff: dict, role: str, seed: int) -> dict:
        c = self.cfg
        return {"role": role, "seed": seed, "levels": c["evaluation.levels"],
                "episodes_per_level": c["evaluation.episodes_per_level"], "lives": c["evaluation.lives"],
                "max_steps": c["evaluation.max_steps"], "frame_skip": c["evaluation.frame_skip"],
                "cap_frames": c["evaluation.cap_frames"], "action_selection": c["evaluation.action_selection"],
                "completion_definition": c["evaluation.completion_definition"], "obs": eff["obs"],
                "control_obs": eff["control_obs"], "nearest_first": eff["nearest_first"],
                "game_source_hash": c["game.source_hash"],
                "evaluator_sha256": db.sha256_file(self.snap / "scripts" / "evaluate.py")}

    def evaluate(self, run_id, attempt_id, ml_run, model: Path, model_sha: str, eff: dict, role: str, seed: int,
                 out: Path, step: int, try_n: int = 1, job: dict | None = None) -> dict | None:
        """One standard test; None on an infrastructure failure. Recorded in
        SQLite (full protocol) and MLflow."""
        from audit_hparam_campaign import check_eval_file

        con, c = self.con(), self.cfg
        proto = self.protocol(eff, role, seed)
        done = con.execute("SELECT results_json FROM evaluations WHERE run_id = ? AND checkpoint_sha256 = ? AND "
                           "protocol_sha256 = ?", (run_id, model_sha, db.sha256_text(db.canonical(proto)))).fetchone()
        if done:  # already recorded (a restarted runner): the same checkpoint and protocol are not rerun
            return json.loads(done["results_json"])
        argv = [self.python, str(self.snap / "scripts" / "evaluate.py"), str(model), "--levels", proto["levels"],
                "--episodes", str(proto["episodes_per_level"]), "--max-steps", str(proto["max_steps"]),
                "--frame-skip", str(proto["frame_skip"]), "--obs", proto["obs"], "--seed", str(seed),
                "--lives", str(proto["lives"]), "--action-selection", proto["action_selection"],
                "--per-level-out", str(out)]
        argv += ["--control-obs"] if proto["control_obs"] else []
        argv += ["--nearest-first"] if proto["nearest_first"] else []
        key = f"{attempt_id}/eval/{role}/{seed}" + (f"/try{try_n}" if try_n > 1 else "")
        rc, seconds = self.run_child(job, "eval", argv, out.with_suffix(".out"), out.with_suffix(".err"),
                                     self.eval_hard, key)
        if rc != 0 or not out.exists():
            store.add_event(con, "failed", {"stage": f"evaluation {role} {seed}", "rc": rc}, run_id=run_id,
                            attempt_id=attempt_id)
            self.log(f"evaluation failed {model} {role} {seed}: exit {rc}")
            return None
        if db.sha256_file(model) != model_sha:
            raise SystemicError(f"{model} changed during evaluation")
        summary, problems = check_eval_file(out, proto["episodes_per_level"])
        if problems:
            raise SystemicError(f"{out}: {problems[:3]}")
        reported = json.loads(out.read_text())["protocol"]
        want = {"lives": proto["lives"], "max_steps": proto["max_steps"], "frame_skip": proto["frame_skip"],
                "action_selection": proto["action_selection"], "episodes_per_level": proto["episodes_per_level"],
                "seed": seed, "obs": proto["obs"], "control_obs": proto["control_obs"],
                "nearest_first": proto["nearest_first"], "cap_frames": proto["cap_frames"]}
        if {k: reported[k] for k in want} != want:
            raise SystemicError(f"{out}: evaluator ran {reported}, expected {want}")
        raw = json.loads(out.read_text())
        results = {"cleared": summary["cleared"], "died": summary["died"], "timeout": summary["timeout"],
                   "episodes": raw["episodes"], "levels_cleared": raw["levels_cleared"],
                   "kills_per_episode": raw["kills_per_episode"], "mean_score": raw["mean_score"],
                   "per_level_clears": {str(lv): v["clear"] for lv, v in summary["per_level"].items()}}
        eval_id = store.register_evaluation(con, run_id, attempt_id, self.status["game_version_id"], str(model),
                                            model_sha, proto, role, c["evaluation.metric"],
                                            c["evaluation.metric_version"], results, str(out))
        store.add_artifact(con, "evaluation_raw", out, db.sha256_file(out), run_id=run_id, attempt_id=attempt_id,
                           evaluation_id=eval_id)
        from mlflow.entities import Metric

        ts = int(time.time() * 1000)
        client_for(self.uri).log_batch(ml_run, metrics=[
            Metric(f"eval_{role}_s{seed}_{k}", float(results[k]), ts, int(step))
            for k in ("cleared", "died", "timeout", "levels_cleared", "kills_per_episode")])
        client_for(self.uri).set_tag(ml_run, f"exptrack.evaluation.{role}.{seed}", eval_id)
        return results

    # ----------------------------------------------------------- preflight
    def preflight(self) -> dict:
        """Readiness evidence, no performance inference: MLflow answers,
        registration is idempotent, and per arm a two-update training (MLflow
        on, attached to a dispatcher-created run in <experiment>-preflight)
        saves a loadable model that the evaluator accepts. Reports seconds per
        update for each network. Elapsed time counts against the cap."""
        c, con = self.cfg, self.con()
        self.acquire_runner_lock()
        preflight(self.uri)
        ids = self.register()
        again = self.register()
        if again != ids:
            raise SystemicError("registration is not idempotent")
        report = {"registered": ids, "mlflow": self.uri, "arms": {}}
        client = client_for(self.uri)
        exp_id = ensure_experiment(client, c["tracking.mlflow_experiment"] + "-preflight")
        smoke_root = self.root / "preflight_smoke"
        smoke_root.mkdir(exist_ok=True)
        if self.status is None:
            self.status = {"campaign": self.manifest["campaign_id"], "snapshot_commit": self.info["commit"],
                           "manifest_sha256": self.info["manifest_sha256"], "created": iso(),
                           "db": str(self.db_path), "mlflow_tracking_uri": self.uri, **ids,
                           "jobs": {}, "parts": {}, "final_state": "pending"}
        key = f"preflight/{int(time.time())}"
        used = [0.0]

        def bounded(argv: list[str]):
            """One preflight subprocess, bounded by what is left of the aggregate
            preflight allowance; its cost is recorded even if it fails."""
            remaining = PREFLIGHT_RESERVE_SECONDS - used[0]
            if remaining <= 0:
                raise SystemicError("preflight allowance exhausted")
            t = time.time()
            try:
                return subprocess.run(argv, env=self.env, capture_output=True, text=True, timeout=remaining)
            except subprocess.TimeoutExpired:
                raise SystemicError(f"a preflight subprocess exceeded the remaining allowance ({remaining:.0f} s)")
            finally:
                used[0] += time.time() - t
                self.status["parts"][key] = {"elapsed_seconds": round(used[0], 1)}
                self.save()

        for arm in self.arm_order():
            run_id = ids["runs"][self.job_id(arm, c["seeds.training"][c["design.phases"][0]][0])]
            eff = store.reconstruct_run_config(con, run_id)
            steps = eff["num_envs"] * eff["rollout_len"] * 2
            smoke = {**eff, "total_steps": steps, "wall_minutes": 0.0}
            d = smoke_root / arm
            d.mkdir(exist_ok=True)
            (d / "run_config.json").write_text(json.dumps(smoke, indent=1))
            ml = client.create_run(exp_id, run_name=f"preflight-{arm}", tags={
                "exptrack.run_id": run_id, "campaign": self.manifest["campaign_id"], "arm": arm, "preflight": "true"})
            t0 = time.time()
            tr = bounded([self.python, str(self.snap / "scripts" / "train_ppo.py"), "--config",
                          str(d / "run_config.json"), "--run-dir", str(d), "--mlflow-tracking-uri", self.uri,
                          "--mlflow-run-id", ml.info.run_id, "--log-every", "1", "--no-tensorboard", "--quiet"])
            train_s = time.time() - t0
            summ = json.loads((d / "train_summary.json").read_text()) if (d / "train_summary.json").exists() else {}
            run = client.get_run(ml.info.run_id)
            ok = (tr.returncode == 0 and summ.get("updates") == 2 and run.info.status == "FINISHED"
                  and "losses_policy_loss" in run.data.metrics)
            t1 = time.time()
            ev = bounded([self.python, str(self.snap / "scripts" / "evaluate.py"), str(d / "model.pt"),
                          "--levels", c["evaluation.levels"], "--episodes", "1", "--max-steps",
                          str(c["evaluation.max_steps"]), "--frame-skip", str(c["evaluation.frame_skip"]),
                          "--obs", eff["obs"], "--seed", "1", "--lives", str(c["evaluation.lives"]),
                          "--action-selection", c["evaluation.action_selection"],
                          "--per-level-out", str(d / "eval_smoke.json")]
                         + (["--control-obs"] if eff["control_obs"] else [])
                         + (["--nearest-first"] if eff["nearest_first"] else []))
            eval_s = time.time() - t1
            proto = json.loads((d / "eval_smoke.json").read_text())["protocol"] if ev.returncode == 0 else {}
            report["arms"][arm] = {
                "ok": ok and ev.returncode == 0 and proto.get("lives") == c["evaluation.lives"]
                and proto.get("action_selection") == c["evaluation.action_selection"],
                "parameter_count": json.loads(con.execute(
                    "SELECT value_json FROM run_params WHERE run_id = ? AND key = 'network.parameter_count'",
                    (run_id,)).fetchone()[0]),
                "train_seconds_two_updates": round(train_s, 1),
                "seconds_per_update": round(summ.get("seconds", float("nan")) / 2, 2),
                "smoke_eval_seconds_99_episodes": round(eval_s, 1), "mlflow_run_id": ml.info.run_id,
                "stderr_tail": tr.stderr[-300:] if tr.returncode else ""}
        report["preflight_core_minutes"] = round(used[0] / 60, 2)
        report["ok"] = all(a["ok"] for a in report["arms"].values())
        write_json_atomic(self.root / "preflight.json", report)
        store.add_event(con, "campaign_preflight", report, experiment_id=ids["experiment_id"],
                        revision_id=ids["revision_id"])
        fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        return report

    # --------------------------------------------------- selection and final
    def dev_table(self) -> dict:
        """arm -> {seed: mean development clears, ...} plus pooled ranking keys."""
        c = self.cfg
        table = {}
        for arm in self.arm_order():
            rows = [self.status["jobs"][self.job_id(arm, s)] for s in c["seeds.training"][c["design.phases"][0]]]
            con = self.con()
            clears, levels, seed_fractions = [], [], []
            for j in rows:
                c_j = e_j = 0
                for r in con.execute("SELECT results_json FROM evaluations WHERE run_id = ? AND role = 'development' "
                                     "AND checkpoint_sha256 = ?", (j["run_id"], j["model_sha256"])):
                    res = json.loads(r["results_json"])
                    clears.append(res["cleared"])
                    levels.append(res["levels_cleared"])
                    c_j += res["cleared"]
                    e_j += res["episodes"]
                seed_fractions.append(c_j / e_j if e_j else 0.0)
            n_expected = len(rows) * len(c["evaluation.seed_banks"]["development"])
            if len(clears) != n_expected:
                raise SystemicError(f"{arm}: {len(clears)} development evaluations, expected {n_expected}")
            params = con.execute("SELECT value_json FROM run_params WHERE run_id = ? AND key = "
                                 "'network.parameter_count'", (rows[0]["run_id"],)).fetchone()[0]
            table[arm] = {"mean_cleared": sum(clears) / len(clears), "mean_levels_cleared": sum(levels) / len(levels),
                          "parameter_count": json.loads(params), "clears": clears,
                          "min_seed_fraction": min(seed_fractions)}
        return table

    def select_and_finalize(self) -> None:
        c, con = self.cfg, self.con()
        ref = c["design.reference_arm"]
        sel_path = self.root / "selection.json"
        if sel_path.exists():
            selection = json.loads(sel_path.read_text())
        else:
            table = self.dev_table()
            candidates = [a for a in self.arm_order() if a != ref]
            ranked = rank_candidates(table, candidates, c["ranking.tiebreak"])
            seeds = c["seeds.training"][c["design.phases"][0]]
            selection = {
                "selected_arm": ranked[0], "reference_arm": ref, "ranking": ranked, "development": table,
                "rule": c["selection.rule"], "tiebreak": c["ranking.tiebreak"], "frozen": iso(),
                "checkpoints": {a: {str(s): self.status["jobs"][self.job_id(a, s)]["model_sha256"] for s in seeds}
                                for a in (ranked[0], ref)},
                "final_bank": c["evaluation.seed_banks"]["final"]}
            write_json_atomic(sel_path, selection)
            store.add_artifact(con, "selection", sel_path, db.sha256_file(sel_path),
                               experiment_id=self.status["experiment_id"])
            store.add_event(con, "selection_frozen", selection, experiment_id=self.status["experiment_id"],
                            revision_id=self.status["revision_id"])
            self.log(f"selection frozen: {ranked[0]} (development mean {table[ranked[0]]['mean_cleared']:.1f}); "
                     f"opening final bank {c['evaluation.seed_banks']['final']}")
        reason = self.fits(self.final_reservation(), self.committed())
        if reason and self.status.get("final_state") != "done":
            self.log(f"final evaluation not run: {reason}")
            return
        seeds = c["seeds.training"][c["design.phases"][0]]
        blocked = {}
        for arm in (selection["selected_arm"], ref):
            for s in seeds:
                j = self.status["jobs"][self.job_id(arm, s)]
                if j.get("orphan_child"):
                    alive = self.live_children(j)
                    if alive:
                        blocked[self.job_id(arm, s)] = alive
                    else:  # it ended after the restart; its cost was never recorded
                        with self.lock:
                            self.charge_dead_child(j)
                            j.pop("orphan_child", None)
                            self.save()
        if blocked:
            self.log(f"final evaluation blocked: evaluators from a previous runner are still alive {blocked}")
            store.add_event(con, "final_blocked", {"live": blocked}, experiment_id=self.status["experiment_id"])
            return
        final = {}
        for arm in (selection["selected_arm"], ref):
            for s in seeds:
                j = self.status["jobs"][self.job_id(arm, s)]
                if j["model_sha256"] != selection["checkpoints"][arm][str(s)]:
                    raise SystemicError(f"{arm} s{s}: checkpoint differs from the frozen selection")
                eff = store.reconstruct_run_config(con, j["run_id"])
                for fs in c["evaluation.seed_banks"]["final"]:
                    r = self.evaluate_with_retry(j, "final", fs, eff, Path(j["dir"]) / f"eval_final_{fs}.json")
                    if r is None:
                        raise SystemicError(f"final evaluation {arm} s{s} {fs} failed (retry refused or failed)")
                    final[(arm, s, fs)] = r
        with self.lock:
            self.status["final_state"] = "done"
            self.save()
        self.results(selection, final)

    def results(self, selection: dict, final: dict) -> None:
        c, con = self.cfg, self.con()
        sel, ref = selection["selected_arm"], selection["reference_arm"]
        seeds = c["seeds.training"][c["design.phases"][0]]
        fseeds = c["evaluation.seed_banks"]["final"]
        pairs = {}
        for s in seeds:
            gain = sum(final[(sel, s, fs)]["cleared"] - final[(ref, s, fs)]["cleared"] for fs in fseeds) / len(fseeds)
            pairs[str(s)] = gain
        mean_gain = sum(pairs.values()) / len(pairs)
        lo_mean, lo_each = c["acceptance.mean_paired_gain_min"], c["acceptance.each_paired_gain_min"]
        if lo_mean is None and lo_each is None:
            accepted = None  # no threshold rule registered: absolute outcomes are reported, the decision is reviewed
        else:
            accepted = ((lo_mean is None or mean_gain >= lo_mean)
                        and (lo_each is None or min(pairs.values()) >= lo_each))

        def per_level(arm):
            tot = {}
            for s in seeds:
                for fs in fseeds:
                    for lv, n in final[(arm, s, fs)]["per_level_clears"].items():
                        tot[lv] = tot.get(lv, 0) + n
            return tot

        n_ep = len(seeds) * len(fseeds) * c["evaluation.episodes_per_level"]
        pl_sel, pl_ref = per_level(sel), per_level(ref)
        out = {
            "campaign": self.manifest["campaign_id"], "experiment_id": self.status["experiment_id"],
            "revision_id": self.status["revision_id"], "selected_arm": sel, "reference_arm": ref,
            "final_bank": fseeds, "paired_gain_per_training_seed": pairs, "mean_paired_gain": mean_gain,
            "acceptance": {"mean_paired_gain_min": lo_mean, "each_paired_gain_min": lo_each, "met": accepted},
            "final": {f"{a}_s{s}_e{fs}": {k: v for k, v in r.items() if k != "per_level_clears"}
                      for (a, s, fs), r in final.items()},
            "per_level_clears": {sel: pl_sel, ref: pl_ref, "episodes_per_level_pooled": n_ep},
            "levels_gained": sorted((int(lv) for lv in pl_sel if pl_sel[lv] > pl_ref[lv])),
            "levels_regressed": sorted((int(lv) for lv in pl_sel if pl_sel[lv] < pl_ref[lv])),
            "levels_at_least_half": {sel: sum(v * 2 >= n_ep for v in pl_sel.values()),
                                     ref: sum(v * 2 >= n_ep for v in pl_ref.values())},
            "development": selection["development"],
            "allocated_core_hours": self.spent() / 3600, "cap_core_hours": c["budget.aggregate_core_hours"],
            "jobs": {k: {x: j.get(x) for x in ("arm", "seed", "steps", "updates", "train_seconds", "model_sha256",
                                                "mlflow_run_id", "run_id", "attempts", "development")}
                     for k, j in self.status["jobs"].items()},
            "written": iso()}
        absolute = {a: (sum(final[(a, s, fs)]["cleared"] for s in seeds for fs in fseeds),
                        sum(final[(a, s, fs)]["episodes"] for s in seeds for fs in fseeds)) for a in (sel, ref)}
        out["absolute_final"] = {a: {"cleared": c_, "episodes": e_, "fraction": c_ / e_} for a, (c_, e_) in
                                 absolute.items()}
        path = self.root / "results.json"
        write_json_atomic(path, out)
        store.add_artifact(con, "results", path, db.sha256_file(path), experiment_id=self.status["experiment_id"])
        store.add_event(con, "campaign_results", {k: out[k] for k in ("selected_arm", "paired_gain_per_training_seed",
                                                                     "mean_paired_gain", "acceptance",
                                                                     "allocated_core_hours")},
                        experiment_id=self.status["experiment_id"], revision_id=self.status["revision_id"])
        self.log(f"results: {sel} {absolute[sel][0]}/{absolute[sel][1]}, {ref} {absolute[ref][0]}/{absolute[ref][1]} "
                 f"final-bank clears; paired gains {pairs}; rule "
                 f"{'none registered' if accepted is None else ('met' if accepted else 'not met')}; allocated "
                 f"{out['allocated_core_hours']:.2f} core-hours")
