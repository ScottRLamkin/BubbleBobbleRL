"""Materialise Codex's credit512x4-1020 design (discount x GAE lambda) as a runnable manifest.

    .venv/bin/python scripts/campaigns/make_credit512x4_1020.py

Inputs: scripts/campaigns/credit512x4_1020_design.json (sha256 checked), the
opt512x4-1020 design (for the complete source recipe) and the program's
VALIDATED joint development ranking (runs/opt512x4-1020-r2/ranking.json). The
source recipe is ranking.order[0] across all twelve arms (the reference
included); its complete effective configuration is the opt design's shared
training settings plus that arm's overrides. The four arms change only gamma
and gae_lambda. Nothing is chosen here; every value comes from the two designs
and the validated ranking. Written before the ranking existed.
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
from make_opt512x4_1020 import CONSUMED, DESIGN as OPT_DESIGN, DESIGN_SHA256 as OPT_SHA, build as build_program  # noqa: E402

DESIGN = "scripts/campaigns/credit512x4_1020_design.json"
DESIGN_SHA256 = "7f2a061346b7b89cc0f7c17bd395b09acf6915b652033424010856a86187c655"


def build(ranking: dict, ranking_sha256: str) -> dict:
    raw = (REPO / DESIGN).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DESIGN_SHA256:
        raise SystemExit("credit design hash mismatch")
    cd = json.loads(raw)
    od_raw = (REPO / OPT_DESIGN).read_bytes()
    if hashlib.sha256(od_raw).hexdigest() != OPT_SHA or cd["source_design_sha256"] != OPT_SHA \
            or ranking["design_sha256"] != OPT_SHA:
        raise SystemExit("source design hash mismatch")
    od = json.loads(od_raw)
    source_arm = ranking["order"][0]  # across all twelve, reference included
    opt_arms = {a["id"]: a["overrides"] for a in od["design"]["arms"]}
    if sorted(ranking["order"]) != sorted(opt_arms):
        raise SystemExit("ranking does not cover the twelve designed arms")
    source_cfg = validate({**od["shared_training"], **opt_arms[source_arm]})
    locks = cd["user_locked"]
    if (source_cfg["arch"], source_cfg["hidden"], source_cfg["layers"]) != (
            locks["network.arch"], locks["network.mlp.hidden"], locks["network.mlp.layers"]):
        raise SystemExit("source recipe is not the user-locked network")
    arms = dict(cd["arms"])
    for a, over in arms.items():
        if set(over) != {"gamma", "gae_lambda"}:
            raise SystemExit(f"{a}: arms may change only gamma and gae_lambda")
        validate({**source_cfg, **over})
    ref = cd["reference_arm"]
    ref_cfg = validate({**source_cfg, **arms[ref]})
    _, batches = build_program()
    base = next(iter(batches.values()))["experiment"]  # protocol fields verbatim from the opt materialisation
    ev = cd["evaluation"]
    for k, v in ev.items():
        if base[k] != v:
            raise SystemExit(f"{k}: credit design {v!r} differs from the opt protocol {base[k]!r}")
    b = cd["budget"]
    exp = dict(base)
    exp.update({
        "experiment.question": cd["question"],
        "reference.name": f"{ref}: the source recipe {source_arm} at its own gamma/lambda (fresh seeds)",
        "reference.config_sha256": sha256_text(canonical(ref_cfg)),
        "reference.retained_recipe_entering": None, "reference.original_comparator": ref,
        "design.type": "paired_arms_with_selection",
        "design.arms": arms,
        "design.factors": {"campaign": cd["campaign_id"], "design_sha256": DESIGN_SHA256,
                           "source_program": cd["source_program"], "source_design_sha256": OPT_SHA,
                           "source_arm": source_arm, "source_overrides": opt_arms[source_arm],
                           "source_ranking_sha256": ranking_sha256, "source_recipe_rule": cd["source_recipe_rule"],
                           "factors": cd["factors"], "user_locked": locks,
                           "temporary_controls": cd["temporary_controls"],
                           "interpretation": cd["interpretation"], "required_prelaunch_checks":
                               cd["required_prelaunch_checks"]},
        "design.reference_arm": ref,
        "shared.training": source_cfg,
        "seeds.training": {"main": cd["training_seeds"]},
        "seeds.allocation": f"matched: all four arms on each fresh training seed {cd['training_seeds']}",
        "evaluation.seed_banks": {"development": cd["development_banks"], "final": cd["final_banks"]},
        "evaluation.phase_roles": {"main": ["development", "final"]},
        "evaluation.aggregation": "absolute completed episodes / attempts per arm and per training seed; per-level "
                                  "clear/death/timeout counts; selection on mean development clears",
        "search.procedure": "two-level crossed comparison (gamma x gae_lambda) on the validated top recipe of the "
                            "opt512x4-1020 development search",
        "search.order": cd["dispatch_order"],
        "search.consumed_banks": {**CONSUMED, "opt512x4-1020 search": od["development"]["banks"]},
        "budget.per_run_wall_minutes": {"main": float(cd["training_minutes"])},
        "budget.aggregate_core_hours": float(b["round_allocated_core_hours"]),
        "budget.max_concurrent_jobs": b["global_max_concurrent_jobs"], "budget.threads_per_job": b["threads_per_job"],
        "budget.per_evaluation_hard_seconds": float(b["per_evaluation_hard_seconds"]),
        "budget.save_grace_seconds": float(b["save_grace_seconds"]),
        "budget.hard_cutoff": b["hard_cutoff"],
        "ranking.metric": cd["ranking"][0],
        "ranking.tiebreak": cd["ranking"][1:],
        "selection.rule": cd["selection"],
        "acceptance.mean_paired_gain_min": None, "acceptance.each_paired_gain_min": None,
        "tracking.mlflow_experiment": cd["campaign_id"],
    })
    schema.validate_experiment(exp)
    return {"campaign_id": cd["campaign_id"],
            "authorized": "user via CODEX-20261020T064825-0700; assigned in CODEX-20261020T105213-0700",
            "change_note": f"generated from {DESIGN} (sha256 {DESIGN_SHA256[:16]}) with source arm {source_arm} from the "
                           f"validated ranking (sha256 {ranking_sha256[:16]}) by scripts/campaigns/make_credit512x4_1020.py",
            "game_description": next(iter(batches.values()))["game_description"],
            "seed_provenance": cd["seed_check"] + " Rechecked by Fable before registration.",
            "launch_rule": cd["launch_rule"], "freeze_rule": cd["freeze_rule"],
            "experiment": exp}


def main() -> None:
    from exptrack.validate_ranking import validate as validate_ranking

    root = REPO / "runs" / "opt512x4-1020-r2"
    print(json.dumps(validate_ranking(root, REPO / "experiments.sqlite3")))
    rpath = root / "ranking.json"
    manifest = build(json.loads(rpath.read_text()), sha256_file(rpath))
    out = REPO / "scripts" / "campaigns" / "credit512x4_1020.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{out}: source {manifest['experiment']['design.factors']['source_arm']}; "
          f"arms {list(manifest['experiment']['design.arms'])}")


if __name__ == "__main__":
    main()
