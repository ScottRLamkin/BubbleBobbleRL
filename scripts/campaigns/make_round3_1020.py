"""Generate round 3's manifest from lr-1020's frozen outcome.

    .venv/bin/python scripts/campaigns/make_round3_1020.py

Pre-registered before lr-1020's results were known (committed while it was
training). The rule, following docs/experiment-direction-2026-10-19.md
("Continued experiment loop until 08:00"):

- If lr-1020's acceptance rule is met (its selected 1024x2 learning rate beats
  the retained ff12 256x2 reference by the registered rule), round 3 is
  `replicate-1020`: a fresh-seed replication of that winner against ff12
  256x2, two arms on six new training seeds (7501-7506). Adaptive selection
  across rounds means one winning round is not independent confirmation; this
  checks it on seeds that played no part in choosing it.
- Otherwise round 3 is `entropy-1020`: the entropy coefficient at the retained
  reference. ff12's ent_coef (0.0003) is the lowest value the October 19 search
  screened, and every capacity-1020 run ended with low policy entropy (MLflow,
  last 10%: 0.10-0.31). Arms: the reference and ent_coef 0.0001, 0.001, 0.003
  (a factor of about 3 either side, extending below the screened range), all
  else ff12; seeds 7501-7503.

Both: new development (85001/85002) and final (95001/95002) banks; the
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

ENT = (0.0001, 0.001, 0.003)


def build(lr_manifest: dict, sel: dict, res: dict) -> dict:
    e0 = lr_manifest["experiment"]
    shared = dict(e0["shared.training"])
    accepted = bool(res["acceptance"]["met"])
    ref_arm0 = e0["design.reference_arm"]
    ref_over = dict(e0["design.arms"][ref_arm0])
    exp = dict(e0)
    if accepted:
        win = sel["selected_arm"]
        arms = {ref_arm0: ref_over, win: dict(e0["design.arms"][win])}
        name = "replicate-1020"
        exp.update({
            "experiment.question": f"Does lr-1020's selected arm ({win}) beat {ref_arm0} on six fresh training seeds?",
            "design.factors": {"recipe": [ref_arm0, win], "held_fixed": "everything else"},
            "seeds.training": {"main": [7501, 7502, 7503, 7504, 7505, 7506]},
            "seeds.allocation": "matched: both arms on each of six fresh training seeds",
            "budget.max_concurrent_jobs": 6,
            "ranking.metric": "single candidate (no ranking); development bank reported for comparison",
            "selection.rule": f"no selection: {win} is the only candidate; the final bank is opened after all "
                              "checkpoint hashes are frozen",
        })
        ref_name = ref_arm0
    else:
        arms = {ref_arm0: ref_over}
        for v in ENT:
            arms[f"ent{v:g}"] = {**ref_over, "ent_coef": v}
        name = "entropy-1020"
        exp.update({
            "experiment.question": ("At the retained reference (ff12 MLP 256x2), does a different entropy coefficient "
                                    "(0.0001, 0.001, 0.003 vs 0.0003) improve one-hour level completion?"),
            "design.factors": {"ent_coef": [shared["ent_coef"], *ENT], "held_fixed": "every other ff12 setting"},
            "seeds.training": {"main": [7501, 7502, 7503]},
            "ranking.metric": "mean development clears over the three training seeds and two development seeds "
                              "(non-reference arms only)",
            "selection.rule": "the top-ranked non-reference arm is frozen, with its three endpoint checkpoint hashes "
                              "and the reference's three, before the final bank is opened; no candidate switching or "
                              "retuning on the final bank",
        })
        ref_name = ref_arm0
    for a, over in arms.items():
        validate({**shared, **over})
    exp.update({
        "reference.name": f"retained reference after lr-1020: {ref_name}",
        "reference.config_sha256": sha256_text(canonical(validate({**shared, **ref_over}))),
        "design.arms": arms,
        "design.reference_arm": ref_arm0,
        "evaluation.seed_banks": {"development": [85001, 85002], "final": [95001, 95002]},
        "search.procedure": "fixed design pre-registered before lr-1020 results (make_round3_1020.py); adaptive "
                            "across rounds, fixed within this round",
        "search.order": list(arms),
        "tracking.mlflow_experiment": name,
    })
    schema.validate_experiment(exp)
    return {
        "campaign_id": name,
        "authorized": lr_manifest["authorized"],
        "change_note": f"generated from lr-1020 selection ({sel['selected_arm']}) and acceptance "
                       f"({'met' if accepted else 'not met'}) by scripts/campaigns/make_round3_1020.py",
        "game_description": lr_manifest["game_description"],
        "seed_provenance": "training seeds 7501-7506 and evaluation seeds 85001/85002, 95001/95002 appear in no "
                           "campaign manifest, config or run directory name in this repository (checked "
                           "2026-10-19 23:40)",
        "derived_from": {"lr-1020 selection_frozen": sel["frozen"], "selected_arm": sel["selected_arm"],
                         "acceptance_met": accepted},
        "experiment": exp,
    }


def main() -> None:
    lr = json.loads((REPO / "scripts" / "campaigns" / "lr_1020.json").read_text())
    sel = json.loads((REPO / "runs" / "lr-1020" / "selection.json").read_text())
    res = json.loads((REPO / "runs" / "lr-1020" / "results.json").read_text())
    manifest = build(lr, sel, res)
    out = REPO / "scripts" / "campaigns" / (manifest["campaign_id"].replace("-", "_") + ".json")
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    e = manifest["experiment"]
    print(f"{out}: {manifest['campaign_id']}; arms {list(e['design.arms'])}; reference {e['design.reference_arm']}")


if __name__ == "__main__":
    main()
