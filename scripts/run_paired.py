"""Paired comparison of experiment configurations across training seeds.

    python scripts/run_hyperparameter_search.py snapshot --root runs/<id> --manifest scripts/campaigns/<id>.json
    PYTHONPATH=runs/<id>/snapshot/src:runs/<id>/snapshot/scripts \\
        .venv/bin/python runs/<id>/snapshot/scripts/run_paired.py --root runs/<id>

Every arm is a complete experiment file (no defaults) plus the manifest's
overrides and a training seed. Each job trains in one thread, then runs the
standard test on every evaluation seed; jobs run in parallel up to the
manifest's limit. MLflow tracking is mandatory: the campaign refuses to start
unless the service answers, and each job logs to experiment <campaign_id>. Must run from the snapshot. Checks: snapshot file hashes,
exit codes, the exact evaluation schema (audit_hparam_campaign.check_eval_file),
checkpoint hash unchanged through evaluation. Results: status.json (atomic),
events.log, results.json with paired gains (arm minus the reference arm, per
training seed, averaged over evaluation seeds) and the manifest's acceptance
rule. A job's full reservation is checked against the cutoff before dispatch.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

THREADS = {k: "1" for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    snap = root / "snapshot"
    if Path(__file__).resolve().parent != (snap / "scripts").resolve():
        raise SystemExit("run me from the snapshot")
    info = json.loads((root / "snapshot.json").read_text())
    bad = [r for r, h in info["files"].items() if sha256(snap / r) != h]
    if bad:
        raise SystemExit(f"snapshot changed: {bad[:5]}")
    m = json.loads((snap / info["manifest"]).read_text())
    sys.path[:0] = [str(snap / "scripts"), str(snap / "src")]
    from audit_hparam_campaign import check_eval_file
    from hyperparams import validate

    env = {**os.environ, **THREADS, "PYTHONPATH": f"{snap / 'src'}:{snap / 'scripts'}", "PYTHONDONTWRITEBYTECODE": "1"}
    py = info["interpreter"]
    ev = m["evaluation"]
    b = m["budget"]
    cutoff = dt.datetime.fromisoformat(b["hard_cutoff"])
    lock = threading.Lock()
    status_path = root / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {
        "campaign": m["campaign_id"], "snapshot_commit": info["commit"], "manifest_sha256": info["manifest_sha256"],
        "created": iso(), "jobs": {}}

    def log(msg):
        line = f"{iso()} {msg}"
        print(line, flush=True)
        with open(root / "events.log", "a") as f:
            f.write(line + "\n")

    def save():
        status["updated"] = iso()
        tmp = status_path.with_name("status.json.tmp")
        tmp.write_text(json.dumps(status, indent=1))
        os.replace(tmp, status_path)

    # Preflight: every arm's experiment is complete with the overrides.
    for arm, cfg_rel in m["arms"].items():
        cfg = {**json.loads((snap / cfg_rel).read_text()), **m["overrides"], "seed": m["training_seeds"][0]}
        validate(cfg)
    # MLflow tracking is mandatory: no campaign starts unless the service answers.
    from exptrack.mlflow_sink import preflight, resolve_uri

    mlflow_uri = resolve_uri()
    preflight(mlflow_uri)
    status["mlflow_tracking_uri"] = mlflow_uri
    reserve = m["overrides"]["wall_minutes"] * 60 + b["save_grace_seconds"] + b["per_evaluation_hard_seconds"] * len(ev["seeds"])
    jobs = [(arm, s) for s in m["training_seeds"] for arm in m["arms"]]
    for arm, s in jobs:
        status["jobs"].setdefault(f"{arm}_s{s}", {"arm": arm, "seed": s, "state": "queued"})
    save()
    log(f"{m['campaign_id']} start; snapshot {info['commit'][:10]}; {len(jobs)} jobs; pid {os.getpid()}")

    def run(job):
        arm, seed = job
        jid = f"{arm}_s{seed}"
        j = status["jobs"][jid]
        if j["state"] == "done":
            return
        if dt.datetime.now().astimezone() + dt.timedelta(seconds=reserve) > cutoff:
            with lock:
                j.update(state="not_run", error="would end after the cutoff")
                save()
            log(f"not run {jid}: reservation would end after the cutoff")
            return
        d = root / jid
        d.mkdir(exist_ok=True)
        t0 = time.time()
        try:
            argv = [py, str(snap / "scripts" / "train_ppo.py"), "--config", str(snap / m["arms"][arm]),
                    "--seed", str(seed), "--run-dir", str(d), "--wall-start", repr(t0),
                    "--no-tensorboard", "--quiet", "--mlflow-tracking-uri", mlflow_uri,
                    "--experiment", m["campaign_id"]]
            for tag in (f"campaign={m['campaign_id']}", f"arm={arm}", f"training_seed={seed}",
                        f"snapshot_commit={info['commit']}"):
                argv += ["--mlflow-tag", tag]
            for k, v in m["overrides"].items():
                argv += [f"--{k.replace('_', '-')}", str(v)]
            (d / "argv.json").write_text(json.dumps(argv))
            with lock:
                j.update(state="running", started=iso())
                save()
            log(f"start {jid}")
            with open(d / "train.out", "w") as o, open(d / "train.err", "w") as e:
                rc = subprocess.run(argv, env=env, stdout=o, stderr=e,
                                    timeout=m["overrides"]["wall_minutes"] * 60 + b["save_grace_seconds"]).returncode
            if rc != 0 or not (d / "train_summary.json").exists():
                raise RuntimeError(f"training exit {rc}")
            model = d / "model.pt"
            h = sha256(model)
            results = {}
            for es in ev["seeds"]:
                out = d / f"eval_{es}.json"
                eargv = [py, str(snap / "scripts" / "evaluate.py"), str(model), "--levels", ev["levels"],
                         "--episodes", str(ev["episodes_per_level"]), "--max-steps", str(ev["max_steps"]),
                         "--frame-skip", str(ev["frame_skip"]), "--obs", ev["obs"], "--seed", str(es),
                         "--per-level-out", str(out)] + (["--control-obs"] if ev["control_obs"] else [])
                with open(d / f"eval_{es}.out", "w") as o, open(d / f"eval_{es}.err", "w") as e:
                    rc = subprocess.run(eargv, env=env, stdout=o, stderr=e, timeout=b["per_evaluation_hard_seconds"]).returncode
                if rc != 0:
                    raise RuntimeError(f"evaluation {es} exit {rc}")
                summ, probs = check_eval_file(out, ev["episodes_per_level"])
                if probs:
                    raise RuntimeError("; ".join(probs))
                summ.pop("per_level", None)
                results[str(es)] = summ
            if sha256(model) != h:
                raise RuntimeError("model.pt changed during evaluation")
            ts = json.loads((d / "train_summary.json").read_text())
            with lock:
                j.update(state="done", model_sha256=h, results=results, steps=ts["steps"], updates=ts["updates"],
                         elapsed_seconds=round(time.time() - t0, 1), ended=iso())
                save()
            log(f"done {jid}: " + ", ".join(f"seed {s} cleared {r['cleared']}" for s, r in results.items())
                + f"; {ts['steps']:,} steps, {ts['updates']} updates")
        except Exception as exc:  # noqa: BLE001  recorded, never replaced
            with lock:
                j.update(state="failed", error=f"{type(exc).__name__}: {exc}", elapsed_seconds=round(time.time() - t0, 1))
                save()
            log(f"FAILED {jid}: {exc}")

    with ThreadPoolExecutor(max_workers=b["max_concurrent_jobs"]) as pool:
        list(pool.map(run, jobs))

    ref = m["reference_arm"]
    out = {"campaign": m["campaign_id"], "reference": ref, "pairs": {}, "time": iso()}
    for arm in m["arms"]:
        if arm == ref:
            continue
        gains = {}
        for s in m["training_seeds"]:
            x, y = status["jobs"][f"{arm}_s{s}"], status["jobs"][f"{ref}_s{s}"]
            if x["state"] == y["state"] == "done":
                cx = sum(r["cleared"] for r in x["results"].values()) / len(x["results"])
                cy = sum(r["cleared"] for r in y["results"].values()) / len(y["results"])
                gains[str(s)] = {arm: cx, ref: cy, "gain": cx - cy}
        complete = len(gains) == len(m["training_seeds"])
        g = [v["gain"] for v in gains.values()]
        rule = m["acceptance"]
        out["pairs"][arm] = {"seeds": gains, "complete": complete,
                             "mean_gain": sum(g) / len(g) if g else None,
                             "accepted": complete and sum(g) / len(g) >= rule["mean_paired_gain_min"]
                             and min(g) >= rule["each_paired_gain_min"]}
    (root / "results.json").write_text(json.dumps(out, indent=1))
    log(f"results: {json.dumps(out['pairs'])}")
    log("runner finished")


if __name__ == "__main__":
    main()
