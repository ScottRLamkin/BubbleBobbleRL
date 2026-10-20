"""Generate round 5's manifest (the night's final comparison) from round 4's outcome.

    .venv/bin/python scripts/campaigns/make_round5_1020.py

Written after entropy-1020's outcome was known and committed before any
lowlr-1020 (round 4) outcome existed. Following docs/experiment-direction-
2026-10-19.md ("Continued experiment loop until 08:00"), its third option:
fresh-seed replication of the strongest candidate when uncertainty between
training seeds is the main limitation.

Evidence at registration (final banks, paired gain vs ff12 256x2, clears/990):
capacity-1020 mlp1024x2 -114.3; lr-1020 mlp1024x2_lr0.0003 -16.0 (-32/-48/+32);
entropy-1020 ent0.0001 +53.0 (+118.5/-5.0/+45.5), which passed the mean
threshold but failed the no-negative-pair rule. Seed spread is the main
limitation: the reference's own development clears ranged 185-311 across
training seeds tonight.

Rule:
- candidate = lowlr-1020's selected arm if lowlr-1020's acceptance is met or its
  final mean paired gain exceeds +53.0; otherwise entropy-1020's ent0.0001
  (ties go to ent0.0001, the earlier result);
- two arms: the candidate vs ff12 MLP 256x2 (the ORIGINAL comparator), three
  fresh training seeds (7701-7703), one wave of six one-hour jobs;
- new development (87001/87002) and final (97001/97002) banks; the same
  protocol and acceptance rule, applied to this round's fresh pairs ONLY. The
  earlier pairs are reported alongside but not pooled into the decision.
- Retained recipe vs original comparator (revised 2026-10-20 04:30 after
  CODEX-20261020T035056-0700, before any lowlr-1020 outcome): ff12 256x2 is
  always the ORIGINAL comparator (the reference arm). The recipe retained
  ENTERING this round is lowlr-1020's accepted winner if lowlr-1020 met its
  rule, otherwise ff12. Decision: if lowlr-1020 was accepted, a met rule
  supports the retained winner and a failed rule is conflicting evidence
  requiring review (no automatic reset to ff12); if lowlr-1020 was not
  accepted, ff12 stays retained unless this round's rule is met, in which case
  replacing it with the candidate is recommended for review.
- This is one fresh-seed replication after adaptive candidate selection, not
  proof of the strongest general recipe and not a retry until acceptance. The
  earlier rounds' banks informed this choice; they are marked consumed for the
  search (still valid records of their own frozen comparisons, no longer
  untouched holdouts for the whole search).
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

ENTROPY_BEST = ("ent0.0001", {"ent_coef": 0.0001}, 53.0)
CONSUMED_BANKS = {"capacity-1020": [83001, 83002, 93001, 93002], "lr-1020": [84001, 84002, 94001, 94002],
                  "entropy-1020": [85001, 85002, 95001, 95002], "lowlr-1020": [86001, 86002, 96001, 96002]}


def build(low_manifest: dict, low_sel: dict, low_res: dict) -> dict:
    e0 = low_manifest["experiment"]
    shared = dict(e0["shared.training"])
    ref = e0["design.reference_arm"]
    ref_over = dict(e0["design.arms"][ref])
    low_gain = float(low_res["mean_paired_gain"])
    low_accepted = bool(low_res["acceptance"]["met"])
    retained = low_sel["selected_arm"] if low_accepted else ref
    if low_accepted or low_gain > ENTROPY_BEST[2]:
        cand, cand_over, source = (low_sel["selected_arm"], dict(e0["design.arms"][low_sel["selected_arm"]]),
                                   f"lowlr-1020 selected arm (final mean paired gain {low_gain:+.1f}, acceptance "
                                   f"{'met' if low_res['acceptance']['met'] else 'not met'})")
    else:
        cand, cand_over = ENTROPY_BEST[0], {**ref_over, **ENTROPY_BEST[1]}
        source = (f"entropy-1020 ent0.0001 (final mean paired gain +53.0, one pair -5.0); lowlr-1020's selected arm "
                  f"had {low_gain:+.1f}")
    arms = {ref: ref_over, cand: cand_over}
    for over in arms.values():
        validate({**shared, **over})
    exp = dict(e0)
    exp.update({
        "experiment.question": f"On three fresh training seeds, does {cand} beat ff12 MLP 256x2 by the registered rule?",
        "reference.name": (f"{ref} (ff12 256x2) as the ORIGINAL comparator; retained recipe entering this round: "
                           f"{retained}" + (" (lowlr-1020 accepted)" if low_accepted else
                                            " (no round accepted a replacement)")),
        "reference.config_sha256": sha256_text(canonical(validate({**shared, **ref_over}))),
        "design.arms": arms,
        "design.factors": {"recipe": [ref, cand], "candidate_source": source, "held_fixed": "everything else"},
        "design.reference_arm": ref,
        "seeds.training": {"main": [7701, 7702, 7703]},
        "seeds.allocation": "matched: both arms on each of three fresh training seeds (one wave of six jobs)",
        "evaluation.seed_banks": {"development": [87001, 87002], "final": [97001, 97002]},
        "search.procedure": "single pre-registered fresh-seed replication of the strongest candidate "
                            "(make_round5_1020.py, committed before lowlr-1020 outcomes)",
        "search.order": list(arms),
        "ranking.metric": "single candidate (no ranking); development bank reported for comparison",
        "selection.rule": (f"no selection: {cand} is the only candidate; the final bank is opened after all six "
                           "checkpoint hashes are frozen; the decision uses this round's fresh pairs only. "
                           + (f"Entering retained recipe {retained} (lowlr-1020 accepted): rule met supports it; rule "
                              "failed is conflicting evidence requiring review, not a reset to ff12."
                              if low_accepted else
                              "Entering retained recipe ff12: it stays retained unless the rule is met, in which case "
                              f"replacing it with {cand} is recommended for review.")),
        "tracking.mlflow_experiment": "replicate-final-1020",
        "reference.retained_recipe_entering": retained,
        "reference.original_comparator": ref,
        "search.consumed_banks": CONSUMED_BANKS,
    })
    schema.validate_experiment(exp)
    return {
        "campaign_id": "replicate-final-1020",
        "authorized": low_manifest["authorized"],
        "change_note": f"generated by scripts/campaigns/make_round5_1020.py: candidate {cand} ({source})",
        "game_description": low_manifest["game_description"],
        "seed_provenance": "training seeds 7701-7703 and evaluation seeds 87001/87002, 97001/97002 appear in no "
                           "campaign manifest, config or run directory name in this repository (checked "
                           "2026-10-20 03:45)",
        "retained_recipe_entering": retained,
        "original_comparator": ref,
        "consumed_banks": {"banks": CONSUMED_BANKS, "meaning": "these earlier development/final banks informed the "
                           "adaptive choice of this round's candidate; they remain valid records of their own frozen "
                           "comparisons but are not untouched holdouts for the overall search"},
        "derived_from": {"lowlr-1020 selected_arm": low_sel["selected_arm"], "lowlr-1020 mean_paired_gain": low_gain,
                         "lowlr-1020 acceptance_met": bool(low_res["acceptance"]["met"]),
                         "entropy-1020 ent0.0001 mean_paired_gain": 53.0},
        "experiment": exp,
    }


def main() -> None:
    low = json.loads((REPO / "scripts" / "campaigns" / "lowlr_1020.json").read_text())
    sel = json.loads((REPO / "runs" / "lowlr-1020" / "selection.json").read_text())
    res = json.loads((REPO / "runs" / "lowlr-1020" / "results.json").read_text())
    manifest = build(low, sel, res)
    out = REPO / "scripts" / "campaigns" / "replicate_final_1020.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    e = manifest["experiment"]
    print(f"{out}: {manifest['campaign_id']}; arms {list(e['design.arms'])}; reference {e['design.reference_arm']}")


if __name__ == "__main__":
    main()
