"""Validate a search program's joint ranking before it is used.

    PYTHONPATH=scripts .venv/bin/python -m exptrack.validate_ranking runs/<program root> [--db experiments.sqlite3]

Checks, from SQLite and the files, not from the ranking itself:
- every designed arm is present, in exactly one batch, with exactly the
  registered training seeds, each job done, one endpoint per seed whose file
  hash matches the recorded one;
- each endpoint has exactly one development evaluation per registered bank
  seed (no missing, extra or other-bank rows), each with the full attempt count
  (episodes per level x levels) and the registered protocol;
- the per-arm totals, minimum training-seed fractions, order and selection
  recomputed from those rows equal ranking.json under the registered rule.
Raises SystemExit with every problem found; returns a summary otherwise.
(Added 2026-10-20 after CODEX-20261020T072120-0700: batch_results() summed any
matching development rows without asserting the expected banks and counts.)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import db


def validate(root, db_path) -> dict:
    root = Path(root).resolve()
    snap = root / "snapshot"
    info = json.loads((root / "snapshot.json").read_text())
    manifest = json.loads((snap / info["manifest"]).read_text())
    design = json.loads((snap / manifest["design_path"]).read_text())
    if db.sha256_file(snap / manifest["design_path"]) != manifest["design_sha256"]:
        raise SystemExit("design hash mismatch")
    ranking = json.loads((root / "ranking.json").read_text())
    con = db.connect(db_path)
    problems = []
    expected_arms = [a["id"] for a in design["design"]["arms"]]
    arms = {}
    for b in manifest["batches"]:
        bm = json.loads((snap / b["manifest"]).read_text())["experiment"]
        seeds = bm["seeds.training"]["main"]
        banks = bm["evaluation.seed_banks"]["development"]
        attempts = bm["evaluation.episodes_per_level"] * len(range(1, 100)) if bm["evaluation.levels"] == "1-99" else None
        if attempts is None:
            problems.append(f"{b['id']}: unexpected level set {bm['evaluation.levels']}")
            continue
        status = json.loads((root / b["id"] / "status.json").read_text())
        for arm in b["arms"]:
            if arm in arms:
                problems.append(f"{arm} appears in more than one batch")
            runs = {}
            for s in seeds:
                jid = f"{arm}_s{s}"
                j = status["jobs"].get(jid)
                if j is None or j["state"] != "done":
                    problems.append(f"{b['id']}/{jid}: not done ({None if j is None else j['state']})")
                    continue
                model = Path(j["dir"]) / "model.pt"
                if db.sha256_file(model) != j["model_sha256"]:
                    problems.append(f"{jid}: endpoint hash differs from the recorded one")
                rows = con.execute("SELECT protocol_json, results_json FROM evaluations WHERE run_id = ? AND role = "
                                   "'development' AND checkpoint_sha256 = ?", (j["run_id"], j["model_sha256"])).fetchall()
                got = sorted(json.loads(r["protocol_json"])["seed"] for r in rows)
                if got != sorted(banks):
                    problems.append(f"{jid}: development rows for banks {got}, expected exactly {sorted(banks)}")
                cleared = episodes = 0
                for r in rows:
                    proto, res = json.loads(r["protocol_json"]), json.loads(r["results_json"])
                    if res["episodes"] != attempts or res["cleared"] + res["died"] + res["timeout"] != attempts:
                        problems.append(f"{jid} bank {proto['seed']}: {res['episodes']} attempts, expected {attempts}")
                    for k in ("lives", "max_steps", "frame_skip", "action_selection", "episodes_per_level", "levels"):
                        want = bm[f"evaluation.{k}"]
                        if proto[k] != want:
                            problems.append(f"{jid} bank {proto['seed']}: protocol {k}={proto[k]!r}, expected {want!r}")
                    cleared += res["cleared"]
                    episodes += res["episodes"]
                runs[s] = (cleared, episodes)
            if runs and all(e for _, e in runs.values()):
                c = sum(x for x, _ in runs.values())
                e = sum(y for _, y in runs.values())
                arms[arm] = {"cleared": c, "episodes": e, "fraction": c / e,
                             "min_seed_fraction": min(x / y for x, y in runs.values())}
    if sorted(arms) != sorted(expected_arms):
        problems.append(f"arms with complete results {sorted(arms)} differ from the design {sorted(expected_arms)}")
    if not problems:
        for a, v in arms.items():
            r = ranking["arms"].get(a, {})
            if (r.get("cleared"), r.get("episodes")) != (v["cleared"], v["episodes"]) or \
                    abs(r.get("min_seed_fraction", -1) - v["min_seed_fraction"]) > 1e-12:
                problems.append(f"{a}: ranking.json totals differ from SQLite ({r.get('cleared')}/{r.get('episodes')} "
                                f"vs {v['cleared']}/{v['episodes']})")
        order = sorted(arms, key=lambda a: (-arms[a]["fraction"], -arms[a]["min_seed_fraction"], a))
        ref = manifest["ranking"]["reference"]
        selected = next(a for a in order if a != ref)
        if order != ranking["order"] or selected != ranking["selected"]:
            problems.append(f"recomputed order/selection {order}/{selected} differs from ranking.json "
                            f"{ranking['order']}/{ranking['selected']}")
    if problems:
        raise SystemExit("ranking validation failed:\n  " + "\n  ".join(problems))
    return {"ok": True, "arms": len(arms), "selected": ranking["selected"], "order": ranking["order"],
            "totals": {a: f"{v['cleared']}/{v['episodes']}" for a, v in arms.items()}}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("root")
    p.add_argument("--db", default=str(db.DEFAULT_DB))
    a = p.parse_args()
    print(json.dumps(validate(a.root, a.db), indent=1))


if __name__ == "__main__":
    main()
