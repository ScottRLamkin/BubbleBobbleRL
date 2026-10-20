# ff12 vs recipe G on the fully corrected game — October 19, 2026 (paired-1019-v3)

One-hour paired comparison, run at the user's instruction while Codex was out of quota.
Pre-registered in `scripts/campaigns/paired_1019_v3.json` (commit `2aa2548`) before launch.
Ran 17:18–18:19 PDT with `scripts/run_paired.py`; artifacts are in `runs/paired-1019-v3/`.

**Question.** On the fully corrected game, does ff12 still beat recipe G (anchor_G) at one hour,
on fresh evaluation seeds? The game is snapshot `2aa2548`: every fidelity fix of the day,
including the hurry-up and the baron with the pause and move timers the hparam-1019-v2 snapshot
had reversed.

**Design.**
- Arms: the complete experiment files `configs/hparam-1019_anchor_G_screen.json` and
  `configs/hparam-1019_ff12_confirm.json`, each with a 60-minute endpoint.
- Training seeds: 4301–4303.
- Evaluation: the standard test (99 levels × 10 episodes, 900 decisions, sampled actions) on
  seeds 71001 and 71002. Neither these training seeds nor these evaluation seeds had been used
  anywhere before.
- Rule: the hparam-1019 operational rule (mean paired gain ≥ 30 and no negative pair). It is not
  a significance test.
- Budget: 6 single-thread jobs, about 6.3 core-hours including evaluation; cutoff 18:50.

## Result

**The rule is met.** Clears are level completions per 990 episodes, averaged over the two
evaluation seeds.

| Training seed | ff12 | anchor_G | Paired gain |
|---|---|---|---|
| 4301 | 235.5 | 197.0 | +38.5 |
| 4302 | 341.5 | 176.5 | +165.0 |
| 4303 | 350.0 | 187.5 | +162.5 |
| **Mean** | **309.0** | **187.0** | **+122.0** (range +38.5 to +165.0) |

Outcome profile per 990 episodes. Each value is a training seed's mean over the two evaluation
seeds; ranges run over the three training seeds.

| | ff12 | anchor_G |
|---|---|---|
| Clears | 235.5–350.0 | 176.5–197.0 |
| Deaths | 639.0–753.5 | 775.0–797.0 |
| Timeouts | 0.5–1.0 | 16.5–19.0 |
| Kills per episode | 3.30–3.57 | 2.60–2.83 |
| Levels cleared at least once (of 99) | 44.5–59.0 | 34.5–38.5 |

ff12 varies far more across training seeds than recipe G: 235.5 to 350.0, against 176.5 to
197.0. One of three ff12 seeds was only modestly better than its recipe-G pair (+38.5).

## How this fits with the two campaigns (descriptive)

| | ff12 over recipe G, mean paired gain | Game | Evaluation seeds |
|---|---|---|---|
| hparam-1019-v1 | +176.3 | old game (`42ed83d`) | 61001/61002 |
| hparam-1019-v2 | +101.5 | v2 snapshot, baron timers reversed (`d8619ba`) | 61001/61002 (reused) |
| paired-1019-v3 | +122.0 | fully corrected (`2aa2548`) | 71001/71002 (fresh) |

The three are separately trained policy sets on different game versions; v1 and v2 also share
seeds. They are not a matched series. Together they show the advantage persisting across the
game changes. This run is the first with independent evaluation seeds.

## Cost and artifacts

| Item | Value |
|---|---|
| Measured job time | 21,875 single-thread seconds (6.08 core-hours), plus an 11 s dry run |
| Wall time | 61 minutes |
| Failures | none; all checkpoints and evaluation files verified with the exact schema check |
| Gallery | ff12 seed 4301 on all 99 levels (one unselected episode each), in `exports/` |

Seed 4301 was named for display before the results. It turned out to be the weakest ff12 seed, so
the gallery shows the low end of ff12's range: 23 levels cleared in its single episodes. The
clips play about 11% faster than simulated time.

## Limits

- **Selection.** ff12 was chosen by the earlier search, whose screen used one training seed and
  15 minutes; this run confirms it against recipe G, not against the other configurations.
- **Rule.** The acceptance rule is operational. Three training seeds with this much spread do not
  pin down the size of the advantage; the mean gain of +122 has a wide uncertainty.
- **What it measures.** Completion performance only; no navigation competence is claimed.
