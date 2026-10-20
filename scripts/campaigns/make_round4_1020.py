"""Generate round 4's manifest from entropy-1020's frozen outcome.

    .venv/bin/python scripts/campaigns/make_round4_1020.py

Pre-registered before entropy-1020's results were known (committed while it
was training). The rule, following docs/experiment-direction-2026-10-19.md
("Continued experiment loop until 08:00"):

- If entropy-1020's acceptance rule is met (its selected entropy coefficient
  beats ff12 256x2 by the registered rule), round 4 is `replicate-ent-1020`:
  that winner against ff12 256x2 (the ORIGINAL comparator) on six fresh
  training seeds (7601-7606). A failed replication means uncertainty requiring
  review, not an automatic change of the retained recipe.
- Otherwise round 4 is `lowlr-1020`: can a lower learning rate let a larger
  MLP reach or beat ff12 256x2? In lr-1020, on the same seeds and selection
  bank, 1024x2's development clears rose as the rate fell (0.003: 0, 0.001:
  198, 0.0003: 250) and the trend was not bracketed below 0.0003; on the final
  bank 1024x2 at 0.0003 lost by a mean of 16 with one positive pair. Arms: the
  reference; 1024x2 at 0.0001 (extends the trend); 512x2 at 0.0003 (higher
  throughput, untested at a lower rate); 1024x2 at 0.0003 (the lr-1020
  selection, on fresh seeds). Everything else is ff12; seeds 7601-7603.

Both: new development (86001/86002) and final (96001/96002) banks; the
capacity-1020 protocol, ranking, selection, acceptance and per-round budget.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from exptrack import schema  # noqa: E402
from exptrack.db import canonical, sha256_text  # noqa: E402
from hyperparams import validate  # noqa: E402


def build(ent_manifest: dict, sel: dict, res: dict) -> dict:
    e0 = ent_manifest["experiment"]
    shared = dict(e0["shared.training"])
    accepted = bool(res["acceptance"]["met"])
    ref = e0["design.reference_arm"]
    ref_over = dict(e0["design.arms"][ref])
    exp = dict(e0)
    if accepted:
        win = sel["selected_arm"]
        arms = {ref: ref_over, win: dict(e0["design.arms"][win])}
        name = "replicate-ent-1020"
        exp.update({
            "experiment.question": f"Does entropy-1020's selected arm ({win}) beat {ref} on six fresh training seeds?",
            "design.factors": {"recipe": [ref, win], "held_fixed": "everything else"},
            "seeds.training": {"main": [7601, 7602, 7603, 7604, 7605, 7606]},
            "seeds.allocation": "matched: both arms on each of six fresh training seeds",
            "ranking.metric": "single candidate (no ranking); development bank reported for comparison",
            "selection.rule": f"no selection: {win} is the only candidate; the final bank is opened after all "
                              "checkpoint hashes are frozen",
        })
        ref_name = (f"{ref} as the ORIGINAL comparator (entropy-1020 accepted {win}; a failed replication means "
                    "uncertainty requiring review, not an automatic change of the retained recipe)")
    else:
        arms = {ref: ref_over,
                "mlp1024x2_lr0.0001": {**ref_over, "hidden": 1024, "lr": 0.0001},
                "mlp512x2_lr0.0003": {**ref_over, "hidden": 512, "lr": 0.0003},
                "mlp1024x2_lr0.0003": {**ref_over, "hidden": 1024, "lr": 0.0003}}
        name = "lowlr-1020"
        exp.update({
            "experiment.question": ("Can a lower learning rate let a larger MLP (1024x2 at 0.0001 or 0.0003, 512x2 at "
                                    "0.0003) reach or beat ff12 256x2 at one hour?"),
            "design.factors": {"network.mlp.hidden x lr": ["1024 x 0.0001", "512 x 0.0003", "1024 x 0.0003"],
                               "held_fixed": "every other ff12 setting (2 layers, tanh, ent_coef 0.0003, ...)"},
            "seeds.training": {"main": [7601, 7602, 7603]},
            "ranking.metric": "mean development clears over the three training seeds and two development seeds "
                              "(non-reference arms only)",
            "selection.rule": "the top-ranked non-reference arm is frozen, with its three endpoint checkpoint hashes "
                              "and the reference's three, before the final bank is opened; no candidate switching or "
                              "retuning on the final bank",
        })
        ref_name = f"retained reference after entropy-1020: {ref}"
    for over in arms.values():
        validate({**shared, **over})
    exp.update({
        "reference.name": ref_name,
        "reference.config_sha256": sha256_text(canonical(validate({**shared, **ref_over}))),
        "design.arms": arms,
        "design.reference_arm": ref,
        "evaluation.seed_banks": {"development": [86001, 86002], "final": [96001, 96002]},
        "search.procedure": "fixed design pre-registered before entropy-1020 results (make_round4_1020.py); "
                            "adaptive across rounds, fixed within this round",
        "search.order": list(arms),
        "tracking.mlflow_experiment": name,
    })
    schema.validate_experiment(exp)
    return {
        "campaign_id": name,
        "authorized": ent_manifest["authorized"],
        "change_note": f"generated from entropy-1020 selection ({sel['selected_arm']}) and acceptance "
                       f"({'met' if accepted else 'not met'}) by scripts/campaigns/make_round4_1020.py",
        "game_description": ent_manifest["game_description"],
        "seed_provenance": "training seeds 7601-7606 and evaluation seeds 86001/86002, 96001/96002 appear in no "
                           "campaign manifest, config or run directory name in this repository (checked "
                           "2026-10-20 01:45)",
        "derived_from": {"entropy-1020 selection_frozen": sel["frozen"], "selected_arm": sel["selected_arm"],
                         "acceptance_met": accepted},
        "experiment": exp,
    }


def main() -> None:
    ent = json.loads((REPO / "scripts" / "campaigns" / "entropy_1020.json").read_text())
    sel = json.loads((REPO / "runs" / "entropy-1020" / "selection.json").read_text())
    res = json.loads((REPO / "runs" / "entropy-1020" / "results.json").read_text())
    manifest = build(ent, sel, res)
    out = REPO / "scripts" / "campaigns" / (manifest["campaign_id"].replace("-", "_") + ".json")
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    e = manifest["experiment"]
    print(f"{out}: {manifest['campaign_id']}; arms {list(e['design.arms'])}; reference {e['design.reference_arm']}")


if __name__ == "__main__":
    main()
