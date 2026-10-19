"""Read-only auditor for the hparam-1019-v1 campaign artifacts.

    uv run python scripts/audit_hparam_campaign.py runs/hparam-1019            # audit + report to stdout
    uv run python scripts/audit_hparam_campaign.py runs/hparam-1019 --write    # also writes <root>/audit.md

Independent of the runner's own checks: it re-reads every artifact and
recomputes everything the runner decided. It never starts a process, never
writes inside the snapshot or job directories, and never opens a final-bank
evaluation file unless frozen.json exists and predates that file.

Checks (each failure is listed with the job it concerns):
  snapshot      every snapshot file matches snapshot.json; manifest hash
  status        states are known; one record per (phase, config, seed, eval seed)
  training      argv.json parses to exactly the manifest's fixed parameters,
                the configuration's parameters, the phase's training seed and
                minutes, and a fresh start; train_summary has steps and updates
  checkpoints   model.pt still hashes to the recorded value; no two jobs share
                a checkpoint hash
  evaluations   one file per expected seed and no other seed's file; exact
                level keys 1-99; 10 valid labels per level; clear, death and
                timeout totals equal their per-level counts and sum to 990;
                levels_cleared consistent; legacy all_killed equals clears plus
                killed-then-died plus killed-then-timeout; finite kills; the
                status record equals the file
  separation    tuning seeds only in screen/confirmation, final seeds only in
                final jobs; training seeds as the manifest says
  selection     screen ranking and the two chosen configurations recomputed;
                candidate eligibility (three completed runs) and the winner
                recomputed; frozen checkpoint hashes equal the confirmation
                checkpoints; final-bank files written after frozen.json
  final         paired gains and the acceptance rule recomputed
  accounting    reservations, launch-to-exit training seconds, evaluation
                seconds, and the remainder (validator and runner overhead)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

LABELS = {"clear", "death", "timeout"}
LEVEL_KEYS = {str(i) for i in range(1, 100)}
TERMINAL = {"done", "failed", "not_run"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_eval_file(path: Path, episodes_per_level: int = 10) -> tuple[dict | None, list[str]]:
    """Exact schema of one standard-test file. Returns (summary, problems)."""
    probs: list[str] = []
    try:
        r = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        return None, [f"{path.name}: unreadable ({e})"]
    per = r.get("per_level", {})
    n = 99 * episodes_per_level
    if set(per) != LEVEL_KEYS:
        extra, missing = sorted(set(per) - LEVEL_KEYS), sorted(LEVEL_KEYS - set(per), key=int)
        probs.append(f"{path.name}: level keys wrong (extra {extra[:5]}, missing {missing[:5]})")
    bad = [k for k, v in per.items() if len(v) != episodes_per_level or not set(v) <= LABELS]
    if bad:
        probs.append(f"{path.name}: levels with wrong label count or invalid labels: {bad[:5]}")
    counts = {lab: sum(v.count(lab) for v in per.values()) for lab in LABELS}
    for key, lab in (("cleared", "clear"), ("died", "death"), ("timeout", "timeout")):
        if r.get(key) != counts[lab]:
            probs.append(f"{path.name}: {key} {r.get(key)} != per-level count {counts[lab]}")
    if r.get("episodes") != n or sum(r.get(k, 0) for k in ("cleared", "died", "timeout")) != n:
        probs.append(f"{path.name}: totals do not sum to {n}")
    if r.get("levels_cleared") != sum(1 for v in per.values() if "clear" in v):
        probs.append(f"{path.name}: levels_cleared inconsistent")
    if r.get("all_killed") != r.get("cleared", 0) + r.get("killed_all_then_died", 0) + r.get(
            "killed_all_then_timeout", 0):
        probs.append(f"{path.name}: all_killed != cleared + killed_all_then_died + killed_all_then_timeout")
    k = r.get("kills_per_episode")
    if not isinstance(k, (int, float)) or not math.isfinite(k) or k < 0:
        probs.append(f"{path.name}: kills_per_episode not finite and non-negative")
    if probs:
        return None, probs
    return {"cleared": r["cleared"], "died": r["died"], "timeout": r["timeout"], "kills": k * n,
            "seconds": r.get("seconds")}, []


def expected_jobs(m: dict) -> dict:
    """Phase -> training seed(s), minutes, evaluation seeds, from the manifest."""
    return {
        "screen": {"seeds": [m["screen"]["training_seed"]], "minutes": m["screen"]["minutes_per_policy"],
                   "eval_seeds": m["screen"]["evaluation_seeds"]},
        "confirmation": {"seeds": m["confirmation_training"]["training_seeds"],
                         "minutes": m["confirmation_training"]["minutes_per_policy"],
                         "eval_seeds": m["confirmation_training"]["evaluation_seeds"]},
        "final": {"eval_seeds": m["final_test"]["evaluation_seeds"]},
    }


def audit(root: Path, manifest: dict | None = None, parse_args=None) -> dict:
    root = Path(root)
    problems: list[tuple[str, str]] = []
    warn: list[tuple[str, str]] = []

    def bad(where, msg):
        problems.append((where, msg))

    # ---------------------------------------------------------- snapshot
    snap_info = json.loads((root / "snapshot.json").read_text()) if (root / "snapshot.json").exists() else None
    if snap_info:
        mism = [rel for rel, h in snap_info["files"].items()
                if not (root / "snapshot" / rel).exists() or sha256(root / "snapshot" / rel) != h]
        if mism:
            bad("snapshot", f"{len(mism)} files differ from snapshot.json: {mism[:5]}")
        mpath = root / "snapshot" / "scripts/campaigns/hyperparameter_search_1019.json"
        if mpath.exists() and sha256(mpath) != snap_info["manifest_sha256"]:
            bad("snapshot", "manifest hash differs")
        if manifest is None and mpath.exists():
            manifest = json.loads(mpath.read_text())
        if parse_args is None and (root / "snapshot" / "scripts" / "train_ppo.py").exists():
            sys.path[:0] = [str(root / "snapshot" / "scripts"), str(root / "snapshot" / "src")]
            from train_ppo import parse_args  # noqa: F811  the frozen trainer's parser
    if manifest is None:
        raise SystemExit("no manifest: pass one or audit a root with a snapshot")
    exp = expected_jobs(manifest)
    configs = {c["id"]: c for c in manifest["configurations"]}
    epl = manifest["evaluation"]["episodes_per_level"]

    st = json.loads((root / "status.json").read_text())
    jobs = st["jobs"]
    frozen = json.loads((root / "frozen.json").read_text()) if (root / "frozen.json").exists() else None
    frozen_mtime = (root / "frozen.json").stat().st_mtime if frozen else None

    # ------------------------------------------------------------ status
    seen: dict[tuple, str] = {}
    for jid, j in jobs.items():
        if j["state"] not in TERMINAL | {"queued", "running"}:
            bad(jid, f"unknown state {j['state']}")
        key = (j["phase"], j["config"], j.get("seed"), j.get("eval_seed"))
        if key in seen:
            bad(jid, f"duplicate record of {key} (also {seen[key]})")
        seen[key] = jid
        if j["phase"] in ("screen", "confirmation"):
            if j["config"] not in configs:
                bad(jid, f"unknown configuration {j['config']}")
            if j.get("seed") not in exp[j["phase"]]["seeds"]:
                bad(jid, f"training seed {j.get('seed')} not in the {j['phase']} bank")
            if list(j.get("eval_seeds", [])) != list(exp[j["phase"]]["eval_seeds"]):
                bad(jid, f"evaluation seeds {j.get('eval_seeds')} != {exp[j['phase']]['eval_seeds']}")
        elif j["phase"] == "final" and j.get("eval_seed") not in exp["final"]["eval_seeds"]:
            bad(jid, f"final evaluation seed {j.get('eval_seed')} not in the final bank")
    screen_ids = sorted(j["config"] for j in jobs.values() if j["phase"] == "screen")
    if screen_ids != sorted(configs):
        bad("status", "screen jobs are not exactly the 26 configurations")

    # ------------------------------------------- training, checkpoints, evaluations
    summaries: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    for jid, j in jobs.items():
        if j["state"] != "done":
            continue
        d = Path(j["dir"])
        if j["phase"] in ("screen", "confirmation"):
            argv = json.loads((d / "argv.json").read_text())
            if parse_args is not None:
                a = vars(parse_args(argv[1:]))
                want = {**manifest["fixed_parameters"], **configs[j["config"]]["parameters"],
                        "seed": j["seed"], "wall_minutes": exp[j["phase"]]["minutes"], "run_dir": str(d)}
                for k, v in want.items():
                    if k not in a:
                        bad(jid, f"argv has no parameter {k}")
                    elif a[k] != v and not (isinstance(v, float) and abs(a[k] - v) <= 1e-12 * abs(v)):
                        bad(jid, f"argv {k} = {a[k]!r}, manifest {v!r}")
                if a.get("init_model") is not None:
                    bad(jid, "not a fresh start")
            ts = json.loads((d / "train_summary.json").read_text()) if (d / "train_summary.json").exists() else {}
            if not ts.get("steps") or not ts.get("updates"):
                bad(jid, "train_summary missing steps/updates")
            model = d / "model.pt"
            if not model.exists() or sha256(model) != j.get("model_sha256"):
                bad(jid, "model.pt missing or changed since the job recorded its hash")
            elif j["model_sha256"] in hashes:
                bad(jid, f"same checkpoint hash as {hashes[j['model_sha256']]}")
            else:
                hashes[j["model_sha256"]] = jid
            files = {p.name for p in d.glob("eval_*.json")}
            want_files = {f"eval_{s}.json" for s in exp[j["phase"]]["eval_seeds"]}
            if files != want_files:
                bad(jid, f"evaluation files {sorted(files)} != expected {sorted(want_files)}")
            res = {}
            for s in exp[j["phase"]]["eval_seeds"]:
                summ, probs = check_eval_file(d / f"eval_{s}.json", epl) if (d / f"eval_{s}.json").exists() else (
                    None, [f"eval_{s}.json missing"])
                for p in probs:
                    bad(jid, p)
                if summ:
                    rec = j.get("results", {}).get(str(s), {})
                    if rec.get("cleared") != summ["cleared"] or abs(rec.get("kills", -1) - summ["kills"]) > 1e-6:
                        bad(jid, f"status result for seed {s} differs from the file")
                    res[str(s)] = summ
            summaries[jid] = {"train": ts, "results": res}
        else:  # final
            if not frozen:
                bad(jid, "final job exists without frozen.json")
                continue
            out = Path(j["dir"]) / f"eval_{j['eval_seed']}.json"
            if out.exists() and out.stat().st_mtime < frozen_mtime:
                bad(jid, "final-bank file predates frozen.json")
            ck = frozen["checkpoints"].get(f"{j['config']}_s{j['seed']}")
            if not ck or ck["sha256"] != j.get("model_sha256"):
                bad(jid, "final job's checkpoint is not the frozen one")
            elif sha256(Path(ck["model"])) != ck["sha256"]:
                bad(jid, "frozen checkpoint changed after freezing")
            summ, probs = check_eval_file(out, epl) if out.exists() else (None, ["final file missing"])
            for p in probs:
                bad(jid, p)
            if summ:
                summaries[jid] = {"results": {str(j["eval_seed"]): summ}}

    # --------------------------------------------------------- separation
    for jid, j in jobs.items():
        if j["phase"] in ("screen", "confirmation") and j.get("dir") and Path(j["dir"]).exists():
            leaked = [p.name for p in Path(j["dir"]).glob("eval_*.json")
                      if int(p.stem.split("_")[1]) in exp["final"]["eval_seeds"]]
            if leaked:
                bad(jid, f"final-bank seed evaluated outside the final phase: {leaked}")

    # ---------------------------------------------------------- selection
    def mean(jid, key):
        r = summaries[jid]["results"]
        return sum(v[key] for v in r.values()) / len(r)

    screen_done = [jid for jid, j in jobs.items() if j["phase"] == "screen" and jid in summaries
                   and len(summaries[jid]["results"]) == len(exp["screen"]["eval_seeds"])]
    ranked = sorted(screen_done, key=lambda jid: (-mean(jid, "cleared"), -mean(jid, "kills"), jobs[jid]["config"]))
    chosen = [jobs[jid]["config"] for jid in ranked if jobs[jid]["config"] != "anchor_G"][:2]
    screen_final = all(j["state"] in TERMINAL for j in jobs.values() if j["phase"] == "screen")
    if st.get("selection") is not None:
        if not screen_final:
            bad("selection", "selection recorded before every screen job was final")
        if st["selection"]["chosen"] != chosen:
            bad("selection", f"recorded {st['selection']['chosen']} != recomputed {chosen}")
    winner, cand_table = None, []
    if st.get("selection") is not None:
        seeds = exp["confirmation"]["seeds"]
        for c in st["selection"]["chosen"]:
            runs = [f"conf/{c}_s{s}" for s in seeds]
            ok = all(r in summaries and len(summaries[r]["results"]) == len(exp["confirmation"]["eval_seeds"])
                     for r in runs)
            cand_table.append({"config": c, "eligible": ok,
                               "mean_cleared": sum(mean(r, "cleared") for r in runs) / 3 if ok else None,
                               "mean_kills": sum(mean(r, "kills") for r in runs) / 3 if ok else None})
        el = sorted((c for c in cand_table if c["eligible"]), key=lambda c: (-c["mean_cleared"], -c["mean_kills"],
                                                                              c["config"]))
        winner = el[0]["config"] if el else None
        if frozen is not None and frozen.get("winner") != winner:
            bad("selection", f"frozen winner {frozen.get('winner')} != recomputed {winner}")
        if frozen and frozen.get("winner"):
            for key, ck in frozen["checkpoints"].items():
                cfg, s = key.rsplit("_s", 1)
                src = jobs.get(f"conf/{cfg}_s{s}", {})
                if src.get("model_sha256") != ck["sha256"]:
                    bad("frozen", f"{key} hash differs from its confirmation job")

    # -------------------------------------------------------------- final
    final = None
    if frozen and frozen.get("winner"):
        rule = manifest["final_test"]["practical_improvement"]
        pairs = {}
        for s in exp["confirmation"]["seeds"]:
            vals = {}
            for c in (frozen["winner"], "anchor_G"):
                js = [jid for jid, j in jobs.items() if j["phase"] == "final" and j["config"] == c
                      and j["seed"] == s and jid in summaries]
                vals[c] = (sum(summaries[jid]["results"][str(jobs[jid]["eval_seed"])]["cleared"] for jid in js)
                           / len(js)) if len(js) == len(exp["final"]["eval_seeds"]) else None
            g = None if None in vals.values() else vals[frozen["winner"]] - vals["anchor_G"]
            pairs[s] = {**vals, "gain": g}
        gains = [p["gain"] for p in pairs.values()]
        complete = None not in gains
        final = {"pairs": pairs, "complete": complete,
                 "mean_gain": sum(gains) / len(gains) if complete else None,
                 "accepted": complete and sum(gains) / len(gains) >= rule["mean_paired_gain_min"]
                 and min(gains) >= rule["each_paired_gain_min"]}
        if st.get("final") and st["final"].get("accepted") != final["accepted"]:
            bad("final", "recorded acceptance differs from the recomputation")

    # --------------------------------------------------------- accounting
    acct = {"reserved_seconds": sum(j.get("reserved_seconds", 0) for j in jobs.values()),
            "charged_seconds": st.get("charged_seconds"), "train_seconds": 0.0, "eval_seconds": 0.0,
            "job_elapsed_seconds": 0.0, "other_seconds": 0.0}
    for jid, j in jobs.items():
        if "elapsed_seconds" not in j:
            continue
        ev = sum((v.get("seconds") or 0) for v in summaries.get(jid, {}).get("results", {}).values())
        acct["job_elapsed_seconds"] += j["elapsed_seconds"]
        acct["train_seconds"] += j.get("train_seconds", 0)
        acct["eval_seconds"] += ev
        acct["other_seconds"] += j["elapsed_seconds"] - j.get("train_seconds", 0) - ev
    return {"problems": problems, "warnings": warn, "ranked": [(jobs[j]["config"], mean(j, "cleared"),
                                                                 mean(j, "kills")) for j in ranked],
            "chosen": chosen, "candidates": cand_table, "winner": winner, "final": final, "accounting": acct,
            "summaries": summaries, "status": st, "configs": configs}


def render(a: dict) -> str:
    st, jobs, configs = a["status"], a["status"]["jobs"], a["configs"]
    out = [f"# hparam-1019-v1 audit", "", f"Phase {st['phase']}; {len(a['problems'])} problems.", ""]
    for where, msg in a["problems"]:
        out.append(f"- PROBLEM {where}: {msg}")
    out += ["", "## Screen (tuning seeds; clears are level completions per 990)", "",
            "| config | state | lr | ent | gamma | rollout | epochs | clip | steps | updates | clear/death/timeout per seed | mean clears | mean kills |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for jid in st["order"]:
        j = jobs[jid]
        if j["phase"] not in ("screen", "confirmation"):
            continue
        p = configs[j["config"]]["parameters"]
        s = a["summaries"].get(jid, {})
        ts, res = s.get("train", j.get("train_summary", {})), s.get("results", {})
        name = j["config"] if j["phase"] == "screen" else f"{j['config']} (conf s{j['seed']})"
        out.append("| " + " | ".join([
            name, j["state"] + (f": {j['error']}" if j.get("error") else ""),
            *(f"{p[k]:.3g}" for k in ("lr", "ent_coef", "gamma", "rollout_len", "epochs", "clip")),
            f"{ts['steps']:,}" if ts.get("steps") else "", str(ts.get("updates", "")),
            "; ".join(f"{k}: {v['cleared']}/{v['died']}/{v['timeout']}" for k, v in res.items()),
            f"{sum(v['cleared'] for v in res.values()) / len(res):.1f}" if res else "",
            f"{sum(v['kills'] for v in res.values()) / len(res):.0f}" if res else ""]) + " |")
    out += ["", f"Recomputed selection: {a['chosen']}", f"Candidates: {json.dumps(a['candidates'])}",
            f"Recomputed winner: {a['winner']}", f"Final bank: {json.dumps(a['final'])}", "",
            "Accounting (single-thread seconds): " + json.dumps({k: (round(v, 1) if isinstance(v, float) else v)
                                                                 for k, v in a["accounting"].items()})]
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("root")
    p.add_argument("--write", action="store_true", help="also write <root>/audit.md")
    args = p.parse_args()
    a = audit(Path(args.root))
    text = render(a)
    print(text)
    if args.write:
        (Path(args.root) / "audit.md").write_text(text)
    sys.exit(1 if a["problems"] else 0)


if __name__ == "__main__":
    main()
