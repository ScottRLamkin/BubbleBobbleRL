# Hyperparameter search on the v2 game snapshot — October 19, 2026

Campaign `hparam-1019-v2`, run at the user's direct instruction ("Run it again with the new game
settings"). It repeats [hparam-1019-v1](hyperparameter-search-2026-10-19-results.md) with the
same intended numerical design (the 26 configurations, seed banks, budgets, selection and
acceptance rules of [the design](hyperparameter-search-2026-10-19.md)) on the corrected game.
It ran from 12:47 to 15:36 PDT. The manifest is
`scripts/campaigns/hyperparameter_search_1019_v2.json` (SHA256 `db44ff11…`); the snapshot is
`d8619ba`; all artifacts are under `runs/hparam-1019-v2/`. The independent auditor re-checked
every file and recomputed every decision, and found no problems.

## Verdict

**ff12 passed the acceptance rule against anchor_G (recipe G) on the v2 game snapshot too.** Final
bank: seeds 61001 and 61002, opened only after the winner and six checkpoint hashes were frozen.
Clears are level completions per 990 episodes, averaged over the two seeds.

| Training seed | ff12 | anchor_G | Paired gain |
|---|---|---|---|
| 4201 | 318.0 | 176.0 | +142.0 |
| 4202 | 229.5 | 180.5 | +49.0 |
| 4203 | 258.0 | 144.5 | +113.5 |
| **Mean** | **268.5** | **167.0** | **+101.5** (range +49.0 to +142.0) |

The rule required a mean gain of at least 30 and no negative pair; each pair is tested only
against zero. It is an operational acceptance rule, not a calibrated significance test. The pairs
are less uniform than v1's: the smallest is +49.0, against v1's +120.5.

The final bank reuses v1's seeds, so it is not fresh, independent confirmation across campaigns.
Every game and trainer commit between the two snapshots predates v1's final outcomes. That does
not establish that later decisions, such as the v2 manifest's reuse of seeds, were independent of
them.

Outcome profile on the final bank. Each value is a training seed's mean over the two final seeds,
per 990 episodes; ranges run over the three training seeds.

| | ff12 | anchor_G |
|---|---|---|
| Clears | 229.5–318.0 | 144.5–180.5 |
| Deaths | 671.5–760.5 | 797.0–829.5 |
| Timeouts | 0.0–0.5 | 4.0–16.0 |
| Kills per episode | 2.96–3.41 | 2.47–2.71 |
| Levels cleared at least once (of 99) | 47.0–54.0 | 31.5–34.0 |

## Selection path

- **Screen** (15 minutes, training seed 4100, tuning seeds 51001/51002): ff12 206.0, interior06
  200.0, interior08 186.5, ff11 179.0, anchor_G 162.0. The same two finalists as v1. The full
  table is in `runs/hparam-1019-v2/audit.md`, and per-level outcomes in `per_level.csv`.
- **Confirmation** (one hour, training seeds 4201–4203, tuning seeds): ff12 274.3, interior06
  234.3; anchor_G 165.7.
- **Exploratory factorial contrasts** (16 screen corners). They are resolution IV, from one
  training seed at 15 minutes: not causal, not recommendations.

| Factor | v2 contrast | v1 contrast (old game) |
|---|---|---|
| lr (1e-5 to 1e-3) | +42.1 | +21.9 |
| ent_coef (3e-4 to 0.05) | −77.2 | −53.8 |
| discount horizon (32 to 1,024) | +6.2 | +0.8 |
| rollout length (64 to 512) | −15.1 | +18.9 |
| epochs (2 to 8) | −37.4 | −11.2 |
| clip (0.1 to 0.3) | −7.4 | −12.7 |

## Compared with v1 (descriptive only)

The two campaigns differ in game version and in trainer plumbing, and their policies were
trained separately, so these are differences between distributions, not matched effects.

| | v1 (old game) | v2 (corrected game) |
|---|---|---|
| Final-bank mean paired gain, ff12 over anchor_G | +176.3 | +101.5 |
| anchor_G one-hour final-bank clears (mean of 3 seeds) | 145.3 | 167.0 |
| ff12 one-hour final-bank clears (mean of 3 seeds) | 321.7 | 268.5 |
| anchor_G final-bank timeouts per 990 | 296.0–336.5 | 4.0–16.0 |
| anchor_G final-bank deaths per 990 | 489.0–552.0 | 797.0–829.5 |

On the corrected game, recipe G cleared somewhat more and ff12 somewhat less, so the gap narrowed.
Timeouts almost vanished and deaths rose. One explanation consistent with this is the time
pressure the v2 game adds: the hurry-up and an invulnerable chaser, scheduled within the maximum
horizon on every level, though episodes may end earlier. It is untested: neither baron exposure
nor the cause of each death is recorded, and other mechanics changed too. Fewer timeouts are not
evidence of learned navigation.

## Cost

| Item | Core-hours |
|---|---|
| Reserved and charged before dispatch (47 jobs, plus preflight) | 17.70 |
| Measured job time (training, evaluation, validation) | 15.93 |
| Pre-launch dry run and preflights in a scratch root | about 0.12 (434 s measured job time, plus preflights of about 6 s each) |
| Cap | 18 |

Wall time was 2 h 49 min on six single-thread jobs. No job failed and none was refused.

## Applicability

1. **Baron timing.** The v2 snapshot implements the hurry-up and the baron, but with the baron's
   pause and move timers reversed against the original's `SkelNextSequence` (fixed later in
   `63f0a72`). v2's baron moves 40, 36, 36, 32, … frames between fixed 24-frame pauses, where the
   original moves 24 frames between pauses of 40, 40, 36, 36, …. Every arm saw the same game, so
   the comparison is internally consistent. Whether the corrected timers change the ranking is
   unknown.
2. **Not exactly "only the game".** The intended numerical design is the same, but v2 also runs
   the refactored no-defaults trainer, with keyword environment construction and formerly hidden
   constants exposed at their previous values. Parity rests on configurations matching value for
   value and on targeted tests; executable equivalence is not proven.
3. **Design limits as in v1.** The screen used one training seed and 15 minutes, and ff12 sits at a
   corner of the searched bounds. Evaluation files record their seed only through file names.
4. **Seed reuse.** Training seeds and the final bank were the same as v1's (see Verdict).

The winner's gameplay on all 99 levels is in the gallery catalog `exports/index.html`, recorded
from this snapshot's own generator and game (seed-4201 checkpoint, one unselected episode per
level). The GIFs store 60 ms per decision against the simulated 66.7 ms, so they play about 11%
faster than simulated time.
