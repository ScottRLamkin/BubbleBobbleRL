"""Materialise opt512x4-1020's fresh-seed confirmation from the frozen joint ranking.

    .venv/bin/python scripts/campaigns/make_opt512x4_1020_confirm.py

Inputs: Codex's design (sha256 checked; its `confirmation` block) and the
program's frozen ranking (runs/opt512x4-1020-r2/ranking.json). Output:
scripts/campaigns/opt512x4_1020_confirm.json, a paired_arms_with_selection
manifest with the single selected arm and reference_512x4, identical effective
settings except fresh training seeds, the design's banks and cap, and no
threshold rule (Codex decides from absolute outcomes). Written before the
ranking existed; nothing here is chosen.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "campaigns"))

from exptrack import schema  # noqa: E402
from exptrack.db import canonical, sha256_file, sha256_text  # noqa: E402
from hyperparams import validate  # noqa: E402
from make_opt512x4_1020 import CONSUMED, DESIGN, DESIGN_SHA256, build as build_program  # noqa: E402


def build(ranking: dict, ranking_sha256: str) -> dict:
    raw = (REPO / DESIGN).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DESIGN_SHA256 or ranking["design_sha256"] != DESIGN_SHA256:
        raise SystemExit("design hash mismatch")
    d = json.loads(raw)
    conf, dev = d["confirmation"], d["development"]
    ref = dev["reference"]
    sel = ranking["selected"]
    if sel == ref:
        raise SystemExit("the selected arm must be a non-reference arm")
    arms_all = {a["id"]: a["overrides"] for a in d["design"]["arms"]}
    if ranking["selected_overrides"] != arms_all[sel]:
        raise SystemExit("ranking overrides differ from the design")
    _, batches = build_program()
    base = batches[d["design"]["batches"][0]["id"]]["experiment"]  # the protocol and shared settings, verbatim
    shared = validate(dict(d["shared_training"]))
    exp = dict(base)
    exp.update({
        "experiment.question": f"{d['question']} Fresh-seed confirmation of the jointly selected arm {sel} against "
                               f"{ref} on new training seeds and unopened banks.",
        "reference.name": f"{ref}: the inherited recipe rebuilt as MLP 512x4 (user-locked network)",
        "reference.config_sha256": sha256_text(canonical(validate({**shared, **arms_all[ref]}))),
        "reference.retained_recipe_entering": None, "reference.original_comparator": ref,
        "design.type": "paired_arms_with_selection",
        "design.arms": {ref: arms_all[ref], sel: arms_all[sel]},
        "design.factors": {"program": d["program_id"], "design_sha256": DESIGN_SHA256, "phase": "confirmation",
                           "ranking_sha256": ranking_sha256, "ranking_order": ranking["order"], "selected": sel,
                           "confirmation_spec": conf, "user_locked": d["user_locked"]},
        "design.reference_arm": ref,
        "seeds.training": {"main": conf["training_seeds"]},
        "seeds.allocation": f"matched: both arms on each fresh training seed {conf['training_seeds']}",
        "evaluation.seed_banks": {"development": conf["development_banks"], "final": conf["final_banks"]},
        "evaluation.phase_roles": {"main": ["development", "final"]},
        "evaluation.aggregation": "absolute completed episodes / attempts per arm and per training seed; per-level "
                                  "clear/death/timeout counts",
        "budget.per_run_wall_minutes": {"main": float(conf["training_minutes"])},
        "budget.aggregate_core_hours": float(conf["cap_allocated_core_hours"]),
        "search.procedure": "fresh-seed confirmation after the frozen joint ranking of the opt512x4-1020 search",
        "search.order": [ref, sel],
        "search.consumed_banks": {**CONSUMED, "opt512x4-1020 search": dev["banks"]},
        "ranking.metric": "single candidate (no ranking); development bank reported for comparison",
        "ranking.tiebreak": [],
        "selection.rule": f"no selection: {sel} was frozen by the program ranking; {conf['freeze']}; "
                          f"{'no candidate switching on the final bank' if conf['no_candidate_switching_on_final'] else ''}",
        "acceptance.mean_paired_gain_min": None, "acceptance.each_paired_gain_min": None,
        "tracking.mlflow_experiment": f"{d['program_id']}-confirm",
    })
    schema.validate_experiment(exp)
    return {"campaign_id": f"{d['program_id']}-confirm", "program_id": d["program_id"],
            "authorized": f"user via CODEX-20261020T064825-0700 (daytime execution through {d['hard_cutoff']})",
            "change_note": f"generated from {DESIGN} confirmation block and the frozen ranking (sha256 "
                           f"{ranking_sha256[:16]}) by scripts/campaigns/make_opt512x4_1020_confirm.py",
            "game_description": batches[d["design"]["batches"][0]["id"]]["game_description"],
            "seed_provenance": "training seeds 7901-7903 and evaluation seeds 89001/89002, 98001/98002 checked unused "
                               "in SQLite and campaign files at 2026-10-20 06:55",
            "decision": conf["decision"], "experiment": exp}


def main() -> None:
    rpath = REPO / "runs" / "opt512x4-1020-r2" / "ranking.json"
    manifest = build(json.loads(rpath.read_text()), sha256_file(rpath))
    out = REPO / "scripts" / "campaigns" / "opt512x4_1020_confirm.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{out}: arms {list(manifest['experiment']['design.arms'])}")


if __name__ == "__main__":
    main()
