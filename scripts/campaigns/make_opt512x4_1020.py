"""Materialise Codex's frozen opt512x4-1020 design as runnable manifests.

    .venv/bin/python scripts/campaigns/make_opt512x4_1020.py

Input: scripts/campaigns/opt512x4_1020_design.json (Codex's specification; its
sha256 is checked). Output: the program manifest (opt512x4_1020_program.json)
and one complete search_batch experiment manifest per batch
(opt512x4_1020_b1.json ...). Every value comes from the design: shared
training settings, arms and overrides, batches, seeds, development bank,
evaluation protocol, ranking, confirmation and budgets. Nothing is chosen
here; anything the design does not state is reported as an error.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from exptrack import schema  # noqa: E402
from exptrack.db import canonical, sha256_text  # noqa: E402
from hyperparams import validate  # noqa: E402

DESIGN = "scripts/campaigns/opt512x4_1020_design.json"
DESIGN_SHA256 = "0d378836cb6aba99531aff0ea74d5f1ab87fc2b65bd82fb81f808834830679b6"
EXTENSION_USED_BEFORE = 0.0921  # replicate-final-1020 final-bank evaluation (209.4 s) + galleries (122 s) after 06:48:25
CONSUMED = {"capacity-1020": [83001, 83002, 93001, 93002], "lr-1020": [84001, 84002, 94001, 94002],
            "entropy-1020": [85001, 85002, 95001, 95002], "lowlr-1020": [86001, 86002, 96001, 96002],
            "replicate-final-1020": [87001, 87002, 97001, 97002]}


def build() -> tuple[dict, dict[str, dict]]:
    raw = (REPO / DESIGN).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DESIGN_SHA256:
        raise SystemExit("design hash differs from the authorized design")
    d = json.loads(raw)
    shared = validate(dict(d["shared_training"]))
    locks = d["user_locked"]
    if (shared["arch"], shared["hidden"], shared["layers"]) != (locks["network.arch"], locks["network.mlp.hidden"],
                                                                 locks["network.mlp.layers"]):
        raise SystemExit("shared training settings do not match the user-locked network")
    arms = {a["id"]: a["overrides"] for a in d["design"]["arms"]}
    for a, over in arms.items():
        validate({**shared, **over})
    dev, ev, conf, bud = d["development"], d["evaluation"], d["confirmation"], d["extension_budget"]
    batches = d["design"]["batches"]
    ref = dev["reference"]
    batch_manifests = {}
    for k, b in enumerate(batches, 1):
        exp = {
            "experiment.question": f"{d['question']} (search batch {k} of {len(batches)}: {', '.join(b['arms'])})",
            "game.name": d["game"]["game.name"], "game.source_hash": d["game"]["game.source_hash"],
            "game.source_commit": d["game"]["game.source_commit"],
            "reference.name": f"{ref}: the inherited recipe rebuilt as MLP 512x4 (user-locked network)",
            "reference.config_sha256": sha256_text(canonical(validate({**shared, **arms[ref]}))),
            "reference.retained_recipe_entering": None, "reference.original_comparator": ref,
            "design.type": "search_batch",
            "design.arms": {a: arms[a] for a in b["arms"]},
            "design.factors": {"program": d["program_id"], "design_sha256": DESIGN_SHA256, "batch": b["id"],
                               "batch_index": k, "batches": batches, "all_arms": arms,
                               "factor_space": d["design"]["factors"], "method": d["design"]["method"],
                               "design_seed": d["design"]["seed"], "user_locked": locks,
                               "parameter_policy": d["parameter_policy"]},
            "design.reference_arm": ref if ref in b["arms"] else None,
            "design.phases": ["main"],
            "shared.training": shared,
            "seeds.training": {"main": d["design"]["training_seeds"]},
            "seeds.allocation": "matched: all twelve configurations of the program share training seeds "
                                f"{d['design']['training_seeds']} and development bank {dev['banks']} (intentional "
                                "within one predeclared search)",
            "evaluation.levels": ev["evaluation.levels"], "evaluation.episodes_per_level": ev["evaluation.episodes_per_level"],
            "evaluation.seed_banks": {"development": dev["banks"]}, "evaluation.phase_roles": {"main": ["development"]},
            "evaluation.lives": ev["evaluation.lives"], "evaluation.max_steps": ev["evaluation.max_steps"],
            "evaluation.frame_skip": ev["evaluation.frame_skip"], "evaluation.cap_frames": ev["evaluation.cap_frames"],
            "evaluation.action_selection": ev["evaluation.action_selection"],
            "evaluation.completion_definition": ev["evaluation.completion_definition"],
            "evaluation.metric": ev["evaluation.metric"], "evaluation.metric_version": ev["evaluation.metric_version"],
            "evaluation.aggregation": dev["aggregation"], "evaluation.checkpoint": ev["evaluation.checkpoint"],
            "search.procedure": d["design"]["method"],
            "search.order": [a for a in d["design"]["dispatch_order"] if a in b["arms"]],
            "search.consumed_banks": CONSUMED,
            "budget.hardware": "local Apple M4 Pro CPU, one thread per job",
            "budget.per_run_wall_minutes": {"main": float(d["design"]["training_minutes"])},
            "budget.aggregate_core_hours": float(b["cap_allocated_core_hours"]),
            "budget.includes_evaluation": True,
            "budget.max_concurrent_jobs": bud["max_concurrent_jobs"], "budget.threads_per_job": bud["threads_per_job"],
            "budget.per_evaluation_hard_seconds": 90.0, "budget.save_grace_seconds": 15.0,
            "budget.hard_cutoff": d["hard_cutoff"],
            "stopping.rule": f"fixed {d['design']['training_minutes']}-minute deadline-aware wall limit per job counted "
                             "from launch (total_steps 1e9 never binds); no early, futility or performance pruning",
            "ranking.metric": dev["ranking"][0] + " (joint across all three batches, after all 36 jobs)",
            "ranking.tiebreak": dev["ranking"][1:],
            "selection.rule": dev["select"] + "; joint across the program after every batch completes; this batch "
                              "selects nothing and opens no final bank",
            "acceptance.mean_paired_gain_min": None, "acceptance.each_paired_gain_min": None,
            "tracking.mlflow_uri": "http://127.0.0.1:5000", "tracking.mlflow_experiment": b["id"],
            "tracking.required": True,
        }
        schema.validate_experiment(exp)
        batch_manifests[b["id"]] = {
            "campaign_id": b["id"], "program_id": d["program_id"],
            "authorized": f"user via CODEX-20261020T064825-0700 (daytime execution through {d['hard_cutoff']})",
            "change_note": f"materialised from {DESIGN} (sha256 {DESIGN_SHA256}) by scripts/campaigns/make_opt512x4_1020.py",
            "game_description": "game package identical to the paired-1019-v3 snapshot (2aa2548), Baron-timer correction "
                                "included; unchanged since",
            "seed_provenance": d["seed_check"] + " Rechecked by Fable against SQLite runs, evaluation protocols, revisions "
                               "and campaign files at 2026-10-20 06:55: unused.",
            "experiment": exp}
    program = {
        "program_id": d["program_id"], "design_path": DESIGN, "design_sha256": DESIGN_SHA256,
        "authorized_at": d["authorized_at"], "hard_cutoff": d["hard_cutoff"],
        "batches": [{"id": b["id"], "arms": b["arms"], "manifest": f"scripts/campaigns/{b['id'].replace('-', '_')}.json"}
                    for b in batches],
        "ranking": {**dev, "reference": ref},
        "confirmation": conf,
        "budget": {"extension_core_hours": float(bud["allocated_core_hours"]),
                   "extension_used_before_program_core_hours": EXTENSION_USED_BEFORE,
                   "program_cap_core_hours": float(d["reservation"]["program_cap"]),
                   "batch_cap_core_hours": 15.0, "confirmation_cap_core_hours": float(conf["cap_allocated_core_hours"]),
                   "max_concurrent_jobs": bud["max_concurrent_jobs"]},
    }
    return program, batch_manifests


def main() -> None:
    program, batches = build()
    for bid, m in batches.items():
        path = REPO / "scripts" / "campaigns" / f"{bid.replace('-', '_')}.json"
        path.write_text(json.dumps(m, indent=1) + "\n")
        print(f"{path}: arms {list(m['experiment']['design.arms'])}")
    out = REPO / "scripts" / "campaigns" / "opt512x4_1020_program.json"
    out.write_text(json.dumps(program, indent=1) + "\n")
    print(out)


if __name__ == "__main__":
    main()
