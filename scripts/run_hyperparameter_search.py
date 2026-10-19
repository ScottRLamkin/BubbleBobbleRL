"""Runner for the frozen October 19 hyperparameter search (campaign hparam-1019-v1).

Design and protocol are Codex's: docs/hyperparameter-search-2026-10-19.md and
scripts/campaigns/hyperparameter_search_1019.json. This file only executes them.

    python scripts/run_hyperparameter_search.py snapshot   # freeze the committed source (run from the repo)
    <root>/snapshot/... run_hyperparameter_search.py preflight|run|status --root runs/hparam-1019

`snapshot` extracts one git commit into <root>/snapshot (read-only) and records
file hashes, the manifest hash, interpreter and package versions. `preflight`
and `run` must be started from that snapshot with PYTHONPATH pointing into it;
they refuse to run otherwise. Every training and evaluation is a subprocess of
the snapshot's code with one thread.

Scheduling: at most six concurrent single-thread jobs. A training job is
train -> evaluate on each tuning seed, in one slot. anchor_G's three one-hour
confirmation trainings do not depend on the screen, so they are queued first;
the screen follows in the manifest's recorded order; the two selected
candidates' confirmation trainings are queued when the screen has finished;
the final bank is opened only after the winner and six checkpoint hashes are
frozen to disk.

Budget: each job's full allowance (training minutes + 15 s save grace + 90 s
per evaluation) is reserved before dispatch and never refunded; a job is not
dispatched if its reservation would exceed the 18 core-hour cap or end after
the 13:45 PDT cutoff. Such jobs are recorded as not run.

Restart: one runner at a time (lock file with PID). Finished jobs are never
rerun. A job left "running" by a dead runner is refused if its process is
still alive (no duplicate training), otherwise recorded as interrupted and
rerun as a new attempt with a new reservation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

CAMPAIGN = "hparam-1019-v1"
MANIFEST_REL = "scripts/campaigns/hyperparameter_search_1019.json"
MANIFEST_SHA256 = "1d00742bab2cedef69cc706dc42612f859809ea970a9aed6bd060e6cbb976ee9"
PARAM_FLAGS = ("lr", "ent_coef", "gamma", "rollout_len", "epochs", "clip")
THREAD_ENV = {k: "1" for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")}
SNAPSHOT_PATHS = ("src", "scripts", "tests", "pyproject.toml", "uv.lock", "docs/hyperparameter-search-2026-10-19.md")


# ----------------------------------------------------------------- helpers

def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def iso(t: dt.datetime | None = None) -> str:
    return (t or now()).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=False))
    os.replace(tmp, path)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# --------------------------------------------------------------- snapshot

def cmd_snapshot(args) -> None:
    repo = Path(__file__).resolve().parents[1]
    root = (repo / args.root).resolve() if not Path(args.root).is_absolute() else Path(args.root)
    snap = root / "snapshot"
    if snap.exists():
        raise SystemExit(f"{snap} already exists; a snapshot is immutable")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *SNAPSHOT_PATHS, MANIFEST_REL],
                           cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise SystemExit(f"uncommitted changes in snapshot paths; commit first:\n{dirty}")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                            check=True).stdout.strip()
    snap.mkdir(parents=True)
    archive = subprocess.run(["git", "archive", commit, *SNAPSHOT_PATHS], cwd=repo, capture_output=True,
                             check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(snap)], input=archive, check=True)
    manifest = snap / MANIFEST_REL
    if sha256(manifest) != MANIFEST_SHA256:
        raise SystemExit(f"manifest hash {sha256(manifest)} != frozen {MANIFEST_SHA256}")
    files = {str(p.relative_to(snap)): sha256(p) for p in sorted(snap.rglob("*")) if p.is_file()}
    versions = subprocess.run(
        [sys.executable, "-c", "import sys, torch, gymnasium, numpy; print(sys.version.split()[0], torch.__version__, "
                               "gymnasium.__version__, numpy.__version__)"],
        capture_output=True, text=True, check=True).stdout.split()
    info = {"campaign": CAMPAIGN, "commit": commit, "created": iso(), "interpreter": sys.executable,
            "python": versions[0], "torch": versions[1], "gymnasium": versions[2], "numpy": versions[3],
            "manifest_sha256": MANIFEST_SHA256, "files": files}
    write_json_atomic(root / "snapshot.json", info)
    subprocess.run(["chmod", "-R", "a-w", str(snap)], check=True)
    print(f"snapshot of {commit[:10]} in {snap}: {len(files)} files, manifest {MANIFEST_SHA256[:12]}")


# ------------------------------------------------------------- campaign

class Campaign:
    def __init__(self, root: Path, dry_run: bool = False):
        self.root = root
        self.dry_run = dry_run
        self.snap = root / "snapshot"
        here = Path(__file__).resolve()
        if here.parent != (self.snap / "scripts").resolve():
            raise SystemExit(f"run me from the snapshot ({self.snap / 'scripts'}), not {here.parent}")
        self.info = json.loads((root / "snapshot.json").read_text())
        for rel, h in self.info["files"].items():  # nothing in the snapshot changed since it was frozen
            if sha256(self.snap / rel) != h:
                raise SystemExit(f"snapshot file changed: {rel}")
        self.manifest = json.loads((self.snap / MANIFEST_REL).read_text())
        if dry_run:  # exercise scheduling, phases and restart in seconds; never a result
            self.manifest["screen"]["minutes_per_policy"] = 0.1
            self.manifest["confirmation_training"]["minutes_per_policy"] = 0.2
            self.manifest["evaluation"]["episodes_per_level"] = 1
        self.python = self.info["interpreter"]
        self.env = {**os.environ, **THREAD_ENV, "PYTHONPATH": f"{self.snap / 'src'}:{self.snap / 'scripts'}",
                    "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
                    "MLFLOW_TRACKING_URI": "file:///dev/null"}
        b = self.manifest["budget"]
        self.cap_seconds = b["aggregate_allocated_core_hours"] * 3600
        self.cutoff = dt.datetime.fromisoformat(b["hard_cutoff"])
        self.slots = b["max_concurrent_jobs"]
        self.eval_hard = b["per_evaluation_hard_seconds"]
        self.grace = b["per_training_save_grace_seconds"]
        self.configs = {c["id"]: c for c in self.manifest["configurations"]}
        self.lock = threading.Lock()
        self.status_path = root / "status.json"
        self.status = json.loads(self.status_path.read_text()) if self.status_path.exists() else None

    # ------------------------------------------------------------ logging
    def log(self, msg: str) -> None:
        line = f"{iso()} {msg}"
        print(line, flush=True)
        with open(self.root / "events.log", "a") as f:
            f.write(line + "\n")

    def save(self) -> None:
        self.status["updated"] = iso()
        write_json_atomic(self.status_path, self.status)

    # ------------------------------------------------------- job building
    def train_argv(self, cfg_id: str, seed: int, minutes: float, run_dir: Path) -> list[str]:
        fixed = self.manifest["fixed_parameters"]
        params = self.configs[cfg_id]["parameters"]
        argv = []
        for k, v in fixed.items():
            if v is None or v is False:
                continue
            argv += [f"--{k.replace('_', '-')}"] if v is True else [f"--{k.replace('_', '-')}", str(v)]
        for k in PARAM_FLAGS:
            v = params[k]
            argv += [f"--{k.replace('_', '-')}", str(int(v)) if k in ("rollout_len", "epochs") else repr(float(v))]
        argv += ["--seed", str(seed), "--wall-minutes", str(minutes), "--run-dir", str(run_dir)]
        return argv  # the launcher appends --wall-start (its launch time)

    def eval_argv(self, model: Path, seed: int, out: Path) -> list[str]:
        e = self.manifest["evaluation"]
        argv = [str(model), "--levels", e["levels"], "--episodes", str(e["episodes_per_level"]),
                "--max-steps", str(e["max_steps"]), "--frame-skip", str(e["frame_skip"]), "--obs", e["obs"],
                "--seed", str(seed), "--per-level-out", str(out)]
        return argv + (["--control-obs"] if e["control_obs"] else [])

    def reservation(self, job: dict) -> float:
        if job["kind"] == "eval":
            return self.eval_hard
        return job["minutes"] * 60 + self.grace + self.eval_hard * len(job["eval_seeds"])

    def new_status(self) -> dict:
        m = self.manifest
        jobs = {}
        order = []
        for s in m["confirmation_training"]["training_seeds"]:
            jid = f"conf/anchor_G_s{s}"
            jobs[jid] = {"kind": "train", "phase": "confirmation", "config": "anchor_G", "seed": s,
                         "minutes": m["confirmation_training"]["minutes_per_policy"],
                         "eval_seeds": m["confirmation_training"]["evaluation_seeds"], "state": "queued"}
            order.append(jid)
        for c in m["screen"]["order"]:
            jid = f"screen/{c}"
            jobs[jid] = {"kind": "train", "phase": "screen", "config": c, "seed": m["screen"]["training_seed"],
                         "minutes": m["screen"]["minutes_per_policy"],
                         "eval_seeds": m["screen"]["evaluation_seeds"], "state": "queued"}
            order.append(jid)
        return {"campaign": CAMPAIGN, "dry_run": self.dry_run, "manifest_sha256": MANIFEST_SHA256, "snapshot_commit": self.info["commit"],
                "created": iso(), "phase": "screen", "charged_seconds": 0.0, "preflight_seconds": 0.0,
                "order": order, "jobs": jobs, "selection": None, "frozen": None, "final": None,
                "scheduling_note": "anchor_G confirmation trainings queued before the screen (independent of it)"}

    # -------------------------------------------------------- execution
    def run_proc(self, job_id: str, job: dict, argv: list[str], timeout: float, log_name: str) -> int:
        d = Path(job["dir"])
        with open(d / f"{log_name}.out", "w") as out, open(d / f"{log_name}.err", "w") as err:
            p = subprocess.Popen([self.python, *argv], stdout=out, stderr=err, env=self.env, cwd=self.root)
            self.set(job, pid=p.pid)
            try:
                return p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                return -999

    def check_eval(self, path: Path) -> dict:
        e = self.manifest["evaluation"]
        r = json.loads(path.read_text())
        n = 99 * e["episodes_per_level"]
        per = r["per_level"]
        ok = (r["episodes"] == n and r["cleared"] + r["died"] + r["timeout"] == n and len(per) == 99
              and all(len(v) == e["episodes_per_level"] and set(v) <= {"clear", "death", "timeout"} for v in per.values())
              and sum(v.count("clear") for v in per.values()) == r["cleared"]
              and math.isfinite(r["kills_per_episode"]))
        if not ok:
            raise ValueError(f"evaluation artifact {path} fails the schema check")
        return {"cleared": r["cleared"], "kills": r["kills_per_episode"] * n, "died": r["died"],
                "timeout": r["timeout"], "all_killed_legacy": r["all_killed"], "seconds": r.get("seconds")}

    def model_ok(self, model: Path) -> str:
        code = ("import sys, torch; sd = torch.load(sys.argv[1], map_location='cpu', weights_only=True); "
                "assert sd and all(torch.isfinite(v).all() for v in sd.values() if v.is_floating_point())")
        subprocess.run([self.python, "-c", code, str(model)], env=self.env, check=True, timeout=60)
        return sha256(model)

    def set(self, job: dict, **kw) -> None:
        """All job-state changes go through the lock (another thread may be saving)."""
        with self.lock:
            job.update(kw)
            self.save()

    def execute(self, job_id: str) -> None:
        job = self.status["jobs"][job_id]
        t0 = time.time()
        try:
            d = Path(job["dir"])
            d.mkdir(parents=True, exist_ok=True)
            if job["kind"] == "train":
                launch = time.time()
                argv = [str(self.snap / "scripts" / "train_ppo.py"),
                        *self.train_argv(job["config"], job["seed"], job["minutes"], d), "--wall-start", repr(launch)]
                (d / "argv.json").write_text(json.dumps(argv))
                rc = self.run_proc(job_id, job, argv, job["minutes"] * 60 + self.grace, "train")
                self.set(job, train_seconds=round(time.time() - launch, 1))
                summary = d / "train_summary.json"
                if rc != 0 or not summary.exists():
                    raise RuntimeError(f"training exit {rc}" + (" (hard timeout)" if rc == -999 else "")
                                       + ("; no train_summary.json" if not summary.exists() else ""))
                model = d / "model.pt"
                self.set(job, train_summary=json.loads(summary.read_text()), model_sha256=self.model_ok(model))
                results = {}
                for s in job["eval_seeds"]:
                    out = d / f"eval_{s}.json"
                    rc = self.run_proc(job_id, job, [str(self.snap / "scripts" / "evaluate.py"),
                                                     *self.eval_argv(model, s, out)], self.eval_hard, f"eval_{s}")
                    if rc != 0:
                        raise RuntimeError(f"evaluation seed {s} exit {rc}" + (" (hard timeout)" if rc == -999 else ""))
                    results[str(s)] = self.check_eval(out)
                    self.set(job, results=dict(results))
                if sha256(model) != job["model_sha256"]:
                    raise RuntimeError("model.pt changed during evaluation")
            else:  # final-bank evaluation of a frozen checkpoint
                model = Path(job["model"])
                if sha256(model) != job["model_sha256"]:
                    raise RuntimeError("checkpoint does not match its frozen hash")
                out = d / f"eval_{job['eval_seed']}.json"
                rc = self.run_proc(job_id, job, [str(self.snap / "scripts" / "evaluate.py"),
                                                 *self.eval_argv(model, job["eval_seed"], out)], self.eval_hard,
                                   f"eval_{job['eval_seed']}")
                if rc != 0:
                    raise RuntimeError(f"evaluation exit {rc}" + (" (hard timeout)" if rc == -999 else ""))
                self.set(job, results={str(job["eval_seed"]): self.check_eval(out)})
            state, err = "done", None
        except Exception as e:  # noqa: BLE001  recorded, never silently replaced
            state, err = "failed", f"{type(e).__name__}: {e}"
        self.set(job, state=state, error=err, ended=iso(), elapsed_seconds=round(time.time() - t0, 1), pid=None)
        if state == "done":
            r = job.get("results", {})
            self.log(f"done {job_id} in {job['elapsed_seconds']:.0f} s: "
                     + ", ".join(f"seed {s} cleared {v['cleared']} kills {v['kills']:.0f}" for s, v in r.items())
                     + (f"; {job['train_summary']['steps']:,} steps, {job['train_summary']['updates']} updates"
                        if "train_summary" in job else ""))
        else:
            self.log(f"FAILED {job_id}: {err}")

    # -------------------------------------------------------- phase logic
    def mean(self, job: dict, key: str) -> float:
        r = job["results"]
        return sum(v[key] for v in r.values()) / len(r)

    def advance_phases(self) -> None:
        """Called under the lock when nothing is dispatchable: open the next phase."""
        st, jobs = self.status, self.status["jobs"]
        m = self.manifest
        screen = [j for j in jobs.values() if j["phase"] == "screen"]
        if st["selection"] is None and all(j["state"] in ("done", "failed", "not_run") for j in screen):
            ranked = sorted((j for j in screen if j["state"] == "done"),
                            key=lambda j: (-self.mean(j, "cleared"), -self.mean(j, "kills"), j["config"]))
            table = [{"config": j["config"], "mean_cleared": self.mean(j, "cleared"), "mean_kills": self.mean(j, "kills")}
                     for j in ranked]
            chosen = [t["config"] for t in table if t["config"] != "anchor_G"][:2]
            st["selection"] = {"ranked": table, "chosen": chosen, "time": iso(),
                               "excluded": [j["config"] for j in screen if j["state"] != "done"]}
            self.log(f"screen complete; selected {chosen}")
            for c in chosen:
                for s in m["confirmation_training"]["training_seeds"]:
                    jid = f"conf/{c}_s{s}"
                    jobs[jid] = {"kind": "train", "phase": "confirmation", "config": c, "seed": s,
                                 "minutes": m["confirmation_training"]["minutes_per_policy"],
                                 "eval_seeds": m["confirmation_training"]["evaluation_seeds"], "state": "queued"}
                    st["order"].append(jid)
            st["phase"] = "confirmation"
            self.save()
            return
        conf = [j for j in jobs.values() if j["phase"] == "confirmation"]
        if (st["selection"] is not None and st["frozen"] is None
                and all(j["state"] in ("done", "failed", "not_run") for j in conf)):
            seeds = m["confirmation_training"]["training_seeds"]
            cands = []
            for c in st["selection"]["chosen"]:
                runs = [jobs.get(f"conf/{c}_s{s}") for s in seeds]
                if all(r and r["state"] == "done" for r in runs):
                    cands.append({"config": c, "mean_cleared": sum(self.mean(r, "cleared") for r in runs) / len(runs),
                                  "mean_kills": sum(self.mean(r, "kills") for r in runs) / len(runs)})
            anchor = [jobs.get(f"conf/anchor_G_s{s}") for s in seeds]
            cands.sort(key=lambda c: (-c["mean_cleared"], -c["mean_kills"], c["config"]))
            if not cands or not all(a and a["state"] == "done" for a in anchor):
                st["frozen"] = {"winner": None, "candidates": cands, "time": iso(),
                                "reason": "no candidate with three completed runs, or an anchor run missing"}
                st["phase"] = "stopped"
                self.log("cannot open the final bank: " + st["frozen"]["reason"])
                self.save()
                return
            winner = cands[0]["config"]
            ckpts = {f"{c}_s{s}": {"model": jobs[f"conf/{c}_s{s}"]["dir"] + "/model.pt",
                                   "sha256": jobs[f"conf/{c}_s{s}"]["model_sha256"]}
                     for c in (winner, "anchor_G") for s in seeds}
            st["frozen"] = {"winner": winner, "candidates": cands, "checkpoints": ckpts, "time": iso()}
            write_json_atomic(self.root / "frozen.json", st["frozen"])  # before the final bank is opened
            self.log(f"winner frozen: {winner}; final bank opens now")
            for key, ck in ckpts.items():
                for e in m["final_test"]["evaluation_seeds"]:
                    jid = f"final/{key}_e{e}"
                    jobs[jid] = {"kind": "eval", "phase": "final", "config": key.rsplit("_s", 1)[0],
                                 "seed": int(key.rsplit("_s", 1)[1]), "eval_seed": e, "model": ck["model"],
                                 "model_sha256": ck["sha256"], "state": "queued"}
                    st["order"].append(jid)
            st["phase"] = "final"
            self.save()
            return
        final = [j for j in jobs.values() if j["phase"] == "final"]
        if st["frozen"] and st["frozen"].get("winner") and st["final"] is None and final and all(
                j["state"] in ("done", "failed", "not_run") for j in final):
            w, seeds = st["frozen"]["winner"], m["confirmation_training"]["training_seeds"]
            pairs = {}
            for s in seeds:
                def clears(c):
                    js = [j for j in final if j["config"] == c and j["seed"] == s and j["state"] == "done"]
                    return (sum(j["results"][str(j["eval_seed"])]["cleared"] for j in js) / len(js)
                            if len(js) == len(m["final_test"]["evaluation_seeds"]) else None)
                cw, ca = clears(w), clears("anchor_G")
                pairs[str(s)] = {"winner": cw, "anchor_G": ca, "gain": None if None in (cw, ca) else cw - ca}
            gains = [p["gain"] for p in pairs.values()]
            rule = m["final_test"]["practical_improvement"]
            complete = None not in gains
            accepted = complete and (sum(gains) / len(gains) >= rule["mean_paired_gain_min"]
                                     and min(gains) >= rule["each_paired_gain_min"])
            st["final"] = {"pairs": pairs, "complete": complete,
                           "mean_gain": sum(gains) / len(gains) if complete else None,
                           "range": [min(gains), max(gains)] if complete else None, "accepted": accepted,
                           "time": iso()}
            st["phase"] = "complete"
            self.log(f"final bank: {json.dumps(st['final'])}")
            self.save()

    # ------------------------------------------------------------- main loop
    def run(self) -> None:
        lock = self.root / "runner.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            other = int(lock.read_text().strip() or 0)
            if pid_alive(other):
                raise SystemExit(f"another runner (pid {other}) holds {lock}")
            self.log(f"stale lock from pid {other}; taking over")
            lock.unlink()
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        try:
            self._run()
        finally:
            lock.unlink(missing_ok=True)

    def _run(self) -> None:
        if not (self.root / "preflight.json").exists() or not json.loads(
                (self.root / "preflight.json").read_text()).get("passed"):
            raise SystemExit("preflight has not passed; no performance run starts on unverified code")
        if self.status is not None and self.status.get("dry_run", False) != self.dry_run:
            raise SystemExit("status.json belongs to a different run mode (dry vs real)")
        if self.dry_run and self.root.name == "hparam-1019":
            raise SystemExit("a dry run must use its own --root")
        if self.status is None:
            self.status = self.new_status()
            self.status["preflight_seconds"] = json.loads((self.root / "preflight.json").read_text())["seconds"]
            self.status["charged_seconds"] = self.status["preflight_seconds"]
            self.log(f"campaign {CAMPAIGN} start; snapshot {self.info['commit'][:10]}; runner pid {os.getpid()}")
        else:
            self.log(f"runner restart, pid {os.getpid()}")
            for jid, j in self.status["jobs"].items():
                if j["state"] == "running":
                    if pid_alive(j.get("pid")):
                        raise SystemExit(f"{jid} still has a live process {j['pid']}; refusing to duplicate it")
                    attempt = j.get("attempt", 1) + 1
                    self.log(f"{jid} was interrupted (attempt {attempt - 1}); requeued as attempt {attempt}")
                    j.update(state="queued", attempt=attempt, interrupted_at=iso())
        self.status["runner_pid"] = os.getpid()
        self.save()
        threads: dict[str, threading.Thread] = {}
        while True:
            with self.lock:
                for jid in [k for k, t in threads.items() if not t.is_alive()]:
                    del threads[jid]
                jobs = self.status["jobs"]
                for jid in self.status["order"]:
                    if len(threads) >= self.slots:
                        break
                    j = jobs[jid]
                    if j["state"] != "queued":
                        continue
                    need = self.reservation(j)
                    if self.status["charged_seconds"] + need > self.cap_seconds:
                        j.update(state="not_run", error="aggregate core-hour cap", ended=iso())
                        self.log(f"not run {jid}: reservation {need:.0f} s exceeds the remaining core-hour cap")
                        continue
                    if now() + dt.timedelta(seconds=need) > self.cutoff:
                        j.update(state="not_run", error="would end after the 13:45 cutoff", ended=iso())
                        self.log(f"not run {jid}: reservation {need:.0f} s would end after the cutoff")
                        continue
                    attempt = j.get("attempt", 1)
                    phase_dir = {"screen": "screen", "confirmation": "conf", "final": "final"}[j["phase"]]
                    name = jid.split("/", 1)[1] + (f".a{attempt}" if attempt > 1 else "")
                    j.update(state="running", started=iso(), reserved_seconds=need, attempt=attempt,
                             dir=str(self.root / phase_dir / name))
                    self.status["charged_seconds"] += need
                    self.save()
                    self.log(f"start {jid} (reserved {need:.0f} s; charged {self.status['charged_seconds'] / 3600:.2f}"
                             f" of {self.cap_seconds / 3600:.0f} core-h)")
                    t = threading.Thread(target=self.execute, args=(jid,), daemon=False)
                    threads[jid] = t
                    t.start()
                before = (self.status["phase"], len(jobs))
                self.advance_phases()  # idempotent; opens a phase as soon as its inputs are final
                changed = (self.status["phase"], len(self.status["jobs"])) != before
                if not threads and not changed and not any(j["state"] == "queued" for j in jobs.values()):
                    break
            time.sleep(2)
        self.write_report()
        self.log(f"runner finished; phase {self.status['phase']}")

    # ----------------------------------------------------------------- report
    def write_report(self) -> None:
        st, jobs = self.status, self.status["jobs"]
        lines = [f"# {CAMPAIGN} report", "", f"Snapshot commit {st['snapshot_commit']}, manifest {MANIFEST_SHA256}.",
                 f"Phase: {st['phase']}. Charged (reserved) core-hours: {st['charged_seconds'] / 3600:.2f} of "
                 f"{self.cap_seconds / 3600:.0f}; summed actual job seconds: "
                 f"{sum(j.get('elapsed_seconds', 0) for j in jobs.values()):.0f}.", "",
                 "Clears are level completions (not legacy all-killed) per 990 episodes.", "",
                 "| job | state | lr | ent | gamma | rollout | epochs | clip | steps | updates | clears per seed | mean clears | mean kills |",
                 "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for jid in st["order"]:
            j = jobs[jid]
            p = self.configs.get(j["config"], {}).get("parameters", {})
            ts = j.get("train_summary", {})
            r = j.get("results", {})
            lines.append("| " + " | ".join([
                jid, j["state"] + (f" ({j['error']})" if j.get("error") else ""),
                *(f"{p[k]:.3g}" if p else "" for k in PARAM_FLAGS),
                f"{ts.get('steps', ''):,}" if ts else "", str(ts.get("updates", "")),
                ", ".join(f"{s}: {v['cleared']}" for s, v in r.items()),
                f"{self.mean(j, 'cleared'):.1f}" if r else "", f"{self.mean(j, 'kills'):.1f}" if r else ""]) + " |")
        lines += ["", "Selection: " + json.dumps(st["selection"]), "", "Frozen: " + json.dumps(st["frozen"]), "",
                  "Final: " + json.dumps(st["final"])]
        (self.root / "report.md").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------- preflight

def cmd_preflight(args) -> None:
    root = Path(args.root).resolve()
    c = Campaign(root)
    t0 = time.time()
    checks = {}

    def check(name, ok, detail=""):
        checks[name] = {"ok": bool(ok), "detail": detail}
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)

    m = c.manifest
    # Imports resolve into the snapshot, one thread.
    probe = subprocess.run([c.python, "-c", "import bubblebobblerl, train_ppo, evaluate, torch; print(bubblebobblerl.__file__);"
                            "print(train_ppo.__file__); print(evaluate.__file__); print(torch.get_num_threads())"],
                           env=c.env, capture_output=True, text=True, cwd=root)
    paths = probe.stdout.split()
    check("imports resolve into the snapshot", probe.returncode == 0 and len(paths) == 4
          and all(p.startswith(str(c.snap)) for p in paths[:3]), " ".join(paths))
    check("one torch thread per job", paths[-1:] == ["1"], f"torch threads {paths[-1:] }")
    # No other campaign or training running.
    ps = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout.splitlines()
    others = [ln for ln in ps if any(s in ln for s in ("train_ppo.py", "evolve.py", "evaluate.py"))
              and str(os.getpid()) not in ln.split()[:1]]
    check("no other training or evaluation processes", not others, "; ".join(o.strip()[:120] for o in others))
    # Design: fractional factorial structure and decoding; interiors in bounds; anchors.
    f = {x["code"]: x for x in m["design"]["factors"]}
    ff = [x for x in m["configurations"] if x["kind"] == "fractional_factorial"]
    X = [x["coded"] for x in ff]
    cols = list(zip(*X))
    bal = all(sum(col) == 0 for col in cols)
    orth = all(sum(a * b for a, b in zip(cols[i], cols[j])) == 0 for i in range(6) for j in range(i + 1, 6))
    two = [[a * b for a, b in zip(cols[i], cols[j])] for i in range(6) for j in range(i + 1, 6)]
    me2 = all(sum(a * b for a, b in zip(col, t)) == 0 for col in cols for t in two)
    gen = all(r[4] == r[0] * r[1] * r[2] and r[5] == r[1] * r[2] * r[3] for r in X)
    check("fractional factorial: 16 unique rows, balanced, orthogonal, E=ABC, F=BCD, mains orthogonal to 2FIs",
          len(ff) == 16 and len({tuple(r) for r in X}) == 16 and bal and orth and gen and me2)

    def decode(code, v):
        lo, hi, sc = f[code]["low"], f[code]["high"], f[code]["scale"]
        if sc in ("log", "discrete_log2"):
            return math.exp(math.log(lo) + (v + 1) / 2 * (math.log(hi) - math.log(lo)))
        return lo + (v + 1) / 2 * (hi - lo)

    names = {"A": "lr", "B": "ent_coef", "D": "rollout_len", "E": "epochs", "F": "clip"}
    dec_ok = True
    for x in ff:
        for i, code in enumerate("ABCDEF"):
            want = decode(code, x["coded"][i])
            got = (1 / (1 - x["parameters"]["gamma"])) if code == "C" else x["parameters"][names[code]]
            dec_ok &= abs(got - want) <= 1e-9 * max(1.0, abs(want))
    check("factorial rows decode to their parameters", dec_ok)
    inb = True
    for x in m["configurations"]:
        if x["kind"] != "latin_hypercube":
            continue
        p = x["parameters"]
        inb &= f["A"]["low"] <= p["lr"] <= f["A"]["high"] and f["B"]["low"] <= p["ent_coef"] <= f["B"]["high"]
        inb &= f["C"]["low"] <= 1 / (1 - p["gamma"]) <= f["C"]["high"] and p["rollout_len"] in (64, 128, 256, 512)
        inb &= f["E"]["low"] <= p["epochs"] <= f["E"]["high"] and f["F"]["low"] <= p["clip"] <= f["F"]["high"]
    check("interior points within bounds", inb)
    ids = [x["id"] for x in m["configurations"]]
    check("26 unique configurations, screen order is a permutation of them",
          len(ids) == 26 and len(set(ids)) == 26 and sorted(m["screen"]["order"]) == sorted(ids))
    check("all parameter rows unique", len({json.dumps(x["parameters"], sort_keys=True)
                                            for x in m["configurations"]}) == 26)
    # Flags: every configuration parses to exactly the manifest's values; fresh starts.
    sys.path[:0] = [str(c.snap / "scripts"), str(c.snap / "src")]
    from train_ppo import parse_args

    flag_ok, notes = True, []
    defaults = vars(parse_args([]))
    for cid in ids:
        a = vars(parse_args(c.train_argv(cid, 4100, 15, root / "x")))
        want = {**m["fixed_parameters"], **c.configs[cid]["parameters"]}
        for k, v in want.items():
            if k not in a:
                flag_ok = False
                notes.append(f"{cid}: unknown parameter {k}")
            elif (a[k] != v) and not (isinstance(v, float) and abs(a[k] - v) <= 1e-12 * abs(v)):
                flag_ok = False
                notes.append(f"{cid}: {k} parsed {a[k]!r} != {v!r}")
        flag_ok &= a["init_model"] is None and a["wall_minutes"] == 15 and a["seed"] == 4100 and a["wall_start"] == 0
    unset = {k: v for k, v in defaults.items() if k not in m["fixed_parameters"] and k not in PARAM_FLAGS
             and k not in ("seed", "wall_minutes", "wall_start", "run_dir")}
    check("every configuration's flags parse to the manifest values; fresh start", flag_ok, "; ".join(notes[:5]))
    print("  options left at trainer defaults:", json.dumps(unset), flush=True)
    a = dict(c.configs["anchor_G"]["parameters"])
    check("anchor_G uses the trainer's defaults for the searched parameters",
          all(defaults[k] == a[k] for k in PARAM_FLAGS))
    # Targeted correctness tests from the snapshot's own test suite.
    t = subprocess.run([c.python, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(c.snap / "tests" / "test_env.py"),
                        "-k", "rng or clear or countdown or autoreset or gae or observation or continuation or falling"],
                       env=c.env, capture_output=True, text=True, cwd=c.snap)
    check("targeted tests (RNG, outcome, autoreset/GAE, observation, continuation, falling)",
          t.returncode == 0, t.stdout.strip().splitlines()[-1] if t.stdout.strip() else t.stderr[-300:])
    # Smoke: finite updates, save, load, evaluate (no performance inference).
    smoke = root / "preflight_smoke"
    if smoke.exists():
        subprocess.run(["rm", "-rf", str(smoke)], check=True)
    argv = c.train_argv("anchor_G", 1, 0.5, smoke)
    argv[argv.index("--total-steps") + 1] = "4096"
    tr = subprocess.run([c.python, str(c.snap / "scripts" / "train_ppo.py"), *argv], env=c.env,
                        capture_output=True, text=True, cwd=root, timeout=300)
    summ = json.loads((smoke / "train_summary.json").read_text()) if (smoke / "train_summary.json").exists() else {}
    check("smoke training: two finite updates, summary written", tr.returncode == 0 and summ.get("updates") == 2,
          json.dumps(summ) + tr.stderr[-300:])
    arch = json.loads((smoke / "arch.json").read_text()) if (smoke / "arch.json").exists() else {}
    check("smoke arch.json records the manifest network and observation",
          arch.get("obs") == "ego" and arch.get("control_obs") is True and arch.get("hidden") == 256
          and arch.get("layers") == 2 and arch.get("act") == "tanh", json.dumps(arch))
    try:
        sha = c.model_ok(smoke / "model.pt")
        ok = True
    except Exception as e:  # noqa: BLE001
        sha, ok = str(e), False
    check("smoke model loads and is finite", ok, sha[:16])
    ev = subprocess.run([c.python, str(c.snap / "scripts" / "evaluate.py"), str(smoke / "model.pt"), "--levels", "1-2",
                         "--episodes", "1", "--obs", "ego", "--control-obs", "--seed", "1",
                         "--per-level-out", str(smoke / "eval.json")], env=c.env, capture_output=True, text=True,
                        cwd=root, timeout=120)
    r = json.loads((smoke / "eval.json").read_text()) if (smoke / "eval.json").exists() else {}
    check("smoke evaluation runs and writes per-level outcomes", ev.returncode == 0 and r.get("episodes") == 2
          and set(r.get("per_level", {})) == {"1", "2"}, ev.stderr[-300:])
    bad = subprocess.run([c.python, str(c.snap / "scripts" / "evaluate.py"), str(smoke / "model.pt"), "--levels", "1",
                          "--episodes", "1", "--control-obs"], env=c.env, capture_output=True, text=True, cwd=root,
                         timeout=120)
    check("a mismatched observation is refused", bad.returncode != 0 and "trained with observation" in bad.stderr)
    seconds = round(time.time() - t0, 1)
    passed = all(v["ok"] for v in checks.values()) and seconds <= 60 * m["budget"]["preflight_max_core_minutes"]
    write_json_atomic(root / "preflight.json", {"passed": passed, "seconds": seconds, "time": iso(),
                                                "snapshot_commit": c.info["commit"], "checks": checks,
                                                "trainer_defaults_not_in_manifest": unset})
    print(f"preflight {'PASSED' if passed else 'FAILED'} in {seconds} s", flush=True)
    if not passed:
        raise SystemExit(1)


def cmd_status(args) -> None:
    root = Path(args.root).resolve()
    st = json.loads((root / "status.json").read_text())
    counts: dict[str, int] = {}
    for j in st["jobs"].values():
        counts[j["state"]] = counts.get(j["state"], 0) + 1
    print(f"{st['campaign']} phase {st['phase']}; jobs {counts}; charged {st['charged_seconds'] / 3600:.2f} core-h; "
          f"updated {st['updated']}")
    for jid in st["order"]:
        j = st["jobs"][jid]
        if j["state"] in ("running", "failed", "not_run") or j.get("results"):
            r = ", ".join(f"{s}:{v['cleared']}" for s, v in j.get("results", {}).items())
            print(f"  {jid:32s} {j['state']:8s} {r} {j.get('error') or ''}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["snapshot", "preflight", "run", "status"])
    p.add_argument("--root", default="runs/hparam-1019")
    p.add_argument("--dry-run", action="store_true", help="seconds-long jobs, 1 episode per level; separate root")
    args = p.parse_args()
    if args.command == "snapshot":
        cmd_snapshot(args)
    elif args.command == "preflight":
        cmd_preflight(args)
    elif args.command == "run":
        Campaign(Path(args.root).resolve(), dry_run=args.dry_run).run()
    else:
        cmd_status(args)


if __name__ == "__main__":
    main()
