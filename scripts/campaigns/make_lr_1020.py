"""Generate the lr-1020 manifest from capacity-1020's frozen outcome.

    .venv/bin/python scripts/campaigns/make_lr_1020.py

Pre-registered before capacity-1020's results were known (committed while it
was training). The rule, from docs/experiment-direction-2026-10-19.md
("Continued experiment loop until 08:00"):

- architecture: capacity-1020's frozen selected larger arm (selection.json),
  the best tested larger network by the registered development rule;
- retained reference: capacity-1020's reference (ff12 MLP 256x2) unless its
  acceptance rule was met, in which case the selected larger arm (at ff12's
  learning rate) becomes the retained reference;
- candidates: that architecture at learning rates 0.0003, 0.001 and 0.003,
  everything else ff12; a candidate identical to the reference is dropped;
- three new matched training seeds (7401-7403), new development (84001/84002)
  and final (94001/94002) banks; the capacity-1020 protocol, ranking,
  selection, acceptance and per-round budget unchanged.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from exptrack import schema  # noqa: E402
from exptrack.db import canonical, sha256_text  # noqa: E402
from hyperparams import validate  # noqa: E402

LRS = (0.0003, 0.001, 0.003)


def build(cap: dict, sel: dict, res: dict) -> dict:
    e0 = cap["experiment"]
    shared = dict(e0["shared.training"])
    arch = dict(e0["design.arms"][sel["selected_arm"]])
    accepted = bool(res["acceptance"]["met"])
    ref_name = sel["selected_arm"] if accepted else sel["reference_arm"]
    ref_over = dict(e0["design.arms"][ref_name])
    arms = {"reference_" + ref_name: ref_over}
    for lr in LRS:
        # ff12 stores its rate as 0.0010000000000000002 (log-scale design); "0.001" means that exact value
        over = {**arch, "lr": shared["lr"] if math.isclose(lr, shared["lr"], rel_tol=1e-9) else lr}
        if validate({**shared, **over}) == validate({**shared, **ref_over}):
            continue  # identical to the reference: deduplicated
        arms[f"{sel['selected_arm']}_lr{lr:g}"] = over
    ref_arm = "reference_" + ref_name
    exp = dict(e0)
    exp.update({
        "experiment.question": (f"At the best tested larger MLP from capacity-1020 ({sel['selected_arm']}), does the "
                                f"learning rate (0.0003, 0.001, 0.003) improve one-hour level completion relative to "
                                f"the retained reference ({ref_name})?"),
        "reference.name": f"retained reference after capacity-1020: {ref_name} "
                          f"({'acceptance met' if accepted else 'acceptance not met; ff12 256x2 retained'})",
        "reference.config_sha256": sha256_text(canonical(validate({**shared, **ref_over}))),
        "design.arms": arms,
        "design.factors": {"lr": list(LRS), "architecture": sel["selected_arm"],
                           "held_fixed": "every other ff12 setting"},
        "design.reference_arm": ref_arm,
        "seeds.training": {"main": [7401, 7402, 7403]},
        "evaluation.seed_banks": {"development": [84001, 84002], "final": [94001, 94002]},
        "search.procedure": "fixed design pre-registered before capacity-1020 results (make_lr_1020.py); "
                            "adaptive across rounds, fixed within this round",
        "search.order": list(arms),
        "ranking.metric": "mean development clears over the three training seeds and two development seeds "
                          "(non-reference arms only)",
        "selection.rule": "the top-ranked non-reference arm is frozen, with its three endpoint checkpoint hashes and "
                          "the reference's three, before the final bank is opened; no candidate switching or "
                          "retuning on the final bank",
        "tracking.mlflow_experiment": "lr-1020",
    })
    schema.validate_experiment(exp)
    manifest = {
        "campaign_id": "lr-1020",
        "authorized": cap["authorized"] + "; continued loop: CODEX-20261019T205553-0700",
        "change_note": f"generated from capacity-1020 selection ({sel['selected_arm']}) and acceptance "
                       f"({'met' if accepted else 'not met'}) by scripts/campaigns/make_lr_1020.py",
        "game_description": cap["game_description"],
        "seed_provenance": "training seeds 7401-7403 and evaluation seeds 84001/84002, 94001/94002 appear in no "
                           "campaign manifest, config or run directory name in this repository (checked "
                           "2026-10-19 21:30)",
        "derived_from": {"capacity-1020 selection_frozen": sel["frozen"], "selected_arm": sel["selected_arm"],
                         "acceptance_met": accepted},
        "experiment": exp,
    }
    return manifest


def main() -> None:
    cap = json.loads((REPO / "scripts" / "campaigns" / "capacity_1020.json").read_text())
    sel = json.loads((REPO / "runs" / "capacity-1020" / "selection.json").read_text())
    res = json.loads((REPO / "runs" / "capacity-1020" / "results.json").read_text())
    manifest = build(cap, sel, res)
    out = REPO / "scripts" / "campaigns" / "lr_1020.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    e = manifest["experiment"]
    print(f"{out}: arms {list(e['design.arms'])}; reference {e['design.reference_arm']}")


if __name__ == "__main__":
    main()
