# Research synthesis after the overnight search — October 20, 2026

This was written at 06:45, from existing artifacts only: SQLite, MLflow histories, raw evaluation
files and galleries. No new evaluations were run. The final replication's results are reported
separately (`docs/replicate-final-1020-results.md`). Its training curves are included here, but
they were extracted at about 06:35, before its runs ended. The per-level table was refreshed at 07:10
to include its evaluation files.
Supporting data: `docs/synthesis-2026-10-20/`.

## 1. Where performance stands (absolute)

The goal is to solve the game, and no recipe is close to that. Under the standard test (each of
levels 1–99 started fresh, one life, 900 decisions of 60 simulated seconds, sampled actions), the best
recipes tonight complete about **30% of level attempts**. Every development and final evaluation file
from the five rounds is pooled below:

| recipe (game 2aa2548) | runs × eval files | attempts | cleared | died | timed out | levels ≥ 50% | levels never cleared | levels always cleared |
|---|---|---|---|---|---|---|---|---|
| 512×2, lr 0.0003 | 6 × 4 | 23,760 | **7,405 (31.2%)** | 68.7% | 0.1% | 26/99 | 12/99 | 1/99 |
| 256×2, ent_coef 0.0001 | 3 × 4 | 11,880 | 3,322 (28.0%) | 72.0% | 0.1% | 26/99 | 25/99 | 2/99 |
| 256×2, ent_coef 0.001 | 3 × 2 | 5,940 | 1,647 (27.7%) | 72.2% | 0.1% | 26/99 | 33/99 | 6/99 |
| **ff12 256×2** (reference, all rounds) | 15 × 4 | 59,400 | 16,307 (27.5%) | 72.5% | 0.0% | 24/99 | 6/99 | 0/99 |
| 1024×2, lr 0.0001 | 3 × 2 | 5,940 | 1,590 (26.8%) | 73.2% | 0.0% | 24/99 | 27/99 | 0/99 |
| 256×2, ent_coef 0.003 | 3 × 2 | 5,940 | 1,526 (25.7%) | 74.3% | 0.0% | 23/99 | 22/99 | 0/99 |
| 1024×2, lr 0.0003 | 6 × 3 | 17,820 | 4,350 (24.4%) | 75.5% | 0.1% | 22/99 | 19/99 | 0/99 |
| 1024×2, lr 0.001 | 6 × 3 | 17,820 | 3,752 (21.1%) | 78.7% | 0.2% | 19/99 | 29/99 | 2/99 |
| 512×2, lr 0.001 | 3 × 2 | 5,940 | 1,243 (20.9%) | 79.1% | 0.0% | 19/99 | 35/99 | 2/99 |
| 512×3, lr 0.001 | 3 × 2 | 5,940 | 1,084 (18.2%) | 81.8% | 0.0% | 15/99 | 47/99 | 4/99 |
| 1024×2, lr 0.003 | 3 × 2 | 5,940 | 0 (0.0%) | 99.1% | 0.9% | 0/99 | 99/99 | 0/99 |

**How to read the level columns.** The counts depend on how many attempts each recipe had: from
60 per level up to 600 for ff12. A recipe with more attempts is less likely to have "never cleared"
levels. Rows are pooled over the development and final banks, so they are descriptive and not a
ranking. The development banks were also selection banks.

**What fails is survival.**
- Nearly every failed attempt is a death; timeouts are essentially zero for every working recipe.
- Five levels were never cleared by any working recipe tonight: **63, 67, 71, 73 and 85**. ff12 also
  never cleared level 21, in 600 attempts.
- No recipe clears any level reliably. ff12 cleared no level in all 600 of its attempts on it.
- In the newest galleries (seed 7601, one episode per level), most deaths came early:
  - deaths at a median of 105 decisions (reference) and 127 decisions (512×2 lr 0.0003), about 7–8.5
    simulated seconds;
  - a quarter of deaths within about 67–69 decisions, about 4.5 s;
  - the earliest at 30 decisions, 2 s (levels 60 and 68);
  - clears took a median of 186–230 decisions, 12–15 s.
- The final frames for levels 63 and 71 show the player dying among enemies in narrow corridors
  (71) and under falling projectiles (63). This is a tentative reading of 96×64 frames, not a
  classification.

## 2. Coverage: what the search actually tested

**Matched comparisons within a round.** These share training seeds and banks.
- **capacity-1020:** width and depth (256×2, 512×2, 512×3, 1024×2) at ff12's lr 0.001.
- **lr-1020:** lr 0.0003, 0.001 and 0.003 at 1024×2.
- **entropy-1020:** ent_coef 0.0001, 0.0003, 0.001 and 0.003 at 256×2.
- **lowlr-1020:** 1024×2 at lr 0.0001 and 0.0003, 512×2 at lr 0.0003, and 256×2 at lr 0.001.
- **replicate-final-1020:** 512×2 at lr 0.0003 against 256×2 at lr 0.001, on fresh seeds.
- **Earlier, on older game versions:** the October 19 search screened lr, ent_coef, gamma, rollout
  length, epochs and clip at 256×2 (15-minute screen, one seed). paired-1019-v3 compared anchor_G with
  ff12 on the current game.

**Cross-round only.** These were never matched, so their seeds, banks and position in the adaptive
search differ:
- 512×2 at lr 0.001 (capacity-1020) against 512×2 at lr 0.0003 (lowlr-1020): 20.9% against 30.1% of
  attempts.
- 1024×2 at lr 0.001 across capacity-1020 and lr-1020.

**The joint gap.** 256×2 at lr 0.0003 was never trained on the current game. So the lowlr-1020
improvement cannot be split between width and learning rate. The direction document's 2×2 cross
(256/512 × lr 0.0003/0.001) would have resolved that. Since the user locked 512×4, the gap is
recorded rather than scheduled.

**Never varied tonight.** All of these were held at ff12's values:
- every reward weight and gate (clear 10, kill 2, capture 0.1, death 5, timeout 4, time 0.01,
  stationary 0.005 over 120 decisions with a 32-pixel band, score off, pop on, explore off);
- gamma 0.99902 (about a 1024-decision horizon), GAE lambda 0.95, no bootstrapping at truncation;
- 16 environments, rollout length 512, 4 minibatches, 2 epochs, clip 0.1, value coefficient 0.5,
  gradient norm 0.5;
- Adam settings, no learning-rate annealing;
- tanh activation and the initialisation gains;
- the ego observation with control state;
- exposure: all 99 levels sampled uniformly, no curriculum, no grace period, no random starts;
- frame skip 4, one life, the 3600-frame episode cap;
- **training duration (always 60 minutes) and continuation.**

## 3. Learning trajectories

Training-time signals from MLflow, plotted for every seed by steps and by elapsed minutes. They are
not evaluation results.

- `docs/synthesis-2026-10-20/capacity-1020_trajectories.png`
- `docs/synthesis-2026-10-20/lr-1020_trajectories.png`
- `docs/synthesis-2026-10-20/entropy-1020_trajectories.png`
- `docs/synthesis-2026-10-20/lowlr-1020_trajectories.png`
- `docs/synthesis-2026-10-20/replicate-final-1020_trajectories.png`

Mean training-episode clear rate at quarters of each run, from `trajectories.json`:

| recipe | runs | 25% | 50% | 75% | last 10% | final entropy | steps (M) |
|---|---|---|---|---|---|---|---|
| 512×2 lr 0.0003 | 3 | 0.157 | 0.217 | 0.337 | 0.300 | 0.28 | 32.4 |
| 256×2 ent_coef 0.0001 | 3 | 0.207 | 0.213 | 0.297 | 0.298 | 0.21 | 37.4 |
| ff12 256×2 | 12 | 0.177 | 0.212 | 0.242 | 0.272 | 0.22 | 34.7 |
| 1024×2 lr 0.0003 | 6 | 0.188 | 0.203 | 0.213 | 0.247 | 0.25 | 24.6 |
| 1024×2 lr 0.001 | 6 | 0.165 | 0.173 | 0.177 | 0.205 | 0.12 | 25.6 |
| 512×2 lr 0.001 | 3 | 0.190 | 0.220 | 0.213 | 0.194 | 0.15 | 32.7 |
| 1024×2 lr 0.003 | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.00 | 25.0 |

**Observations:**
- For ff12 and the better recipes, the training clear rate is still rising over the last quarter
  of the hour; the figures show no plateau at 60 minutes. These are noisy rolling training
  statistics, not evaluation. They do not show that evaluation would keep improving, but they also
  give no evidence that one hour is enough.
- Entropy falls from about 2.1 nats to about 0.5 within the first 5–10M steps in every run, then
  drifts down slowly. Recipes keep improving after that point, so low entropy alone does not mean
  learning stopped.
- At ff12's lr 0.001, 512×2 declines over the second half (0.220, 0.213, 0.194) and 512×3 is flat
  and noisy. 1024×2 rises slowly from a lower level (0.173, 0.177, 0.205). At lr 0.0003, 512×2 rises
  through the hour.

## 4. Competing hypotheses, ranked

Each is ranked by the evidence for it and by how cheaply the next experiment can test it.

1. **Optimisation settings for the (now locked) larger network.**
   - Evidence: the learning rate changed outcomes enormously for 1024×2 (0% to 24% of attempts),
     and 512×2 at lr 0.0003 is the best recipe so far.
   - ent_coef, clip and epochs were never tested at 512×4.
   - Prediction: a block-1 search on 512×4 (learning rate, entropy, clip, epochs) finds settings
     with clearly higher absolute completion than the inherited recipe.
   - Rejected if every configuration lands within the seed spread of the inherited one.
2. **Training duration or sample budget.**
   - Evidence: training clear rates are still rising at 60 minutes. 1024×2 got about 28% fewer
     steps per hour than 256×2, and 512×2 about 7% fewer.
   - Prediction: continuing the best block-1 configuration for 2–3 hours (a separate, budgeted
     duration experiment) raises absolute evaluation completion.
   - Rejected if extra time leaves the evaluation flat.
   - This is a different question from the one-hour target and must be reported as such.
3. **Survival credit assignment and reward balance.**
   - Evidence: failures are early deaths, not timeouts. The death penalty (5) is half the clear
     bonus (10), and kills pay 2.
   - Prediction: changing death or kill weights, or gamma and lambda, shifts the death time and the
     clear rate.
   - Needs a reward and credit-assignment block (eligible later per the card).
4. **Exposure.**
   - Evidence: under uniform sampling each hard level gets about 1% of training, and hard sampling
     and curriculum were never used.
   - Prediction: weighted exposure raises the clear rate on the never- and rarely-cleared levels
     (63, 67, 71, 73, 85, 21, 60) without large losses elsewhere.
5. **Representation of specific threats.**
   - Evidence: the same few levels fail for every recipe.
   - Prediction: those levels share enemy or projectile types that the ego observation encodes
     poorly. This first needs a diagnostic of per-level death causes, with no training. If confirmed,
     it would point to observation changes, which are allowed within the locked MLP.

## 5. Next experiment (draft for Codex's and the user's review; not registered, not launched)

This instantiates Codex's search card, block 1 (`docs/hyperparameter-search-card-2026-10-20.md`),
which tests hypothesis 1 directly.

- **Network:** MLP 512×4 tanh (user-locked). Everything else uses the retained recipe's effective
  configuration.
- **Configurations:** 12, in `docs/synthesis-2026-10-20/block1_draft_configs.json`:
  - the inherited row (lr 0.0003, ent_coef 0.0003, clip 0.1, epochs 2);
  - 11 Latin-hypercube rows from a fixed generator seed: lr 3e-5 to 1e-3 (log), ent_coef 1e-4 to 3e-2
    (log), clip 0.1 to 0.3 (linear), and epochs {2, 4, 8} balanced 4/4/4 counting the inherited row.
- **Replication:** three fresh matched training seeds per configuration, full 60-minute endpoints,
  36 jobs in three batches of 12. Each batch is capped at 15 core-hours including evaluation.
- **Measures, all absolute:** clears out of attempts, the percentage, per-level clear, death and
  timeout counts, and levels never or always cleared. All seeds are shown; there is no pruning and
  no performance retries.
- **Selection and confirmation:** freeze one configuration, then compare it with the 512×4
  inherited row on three NEW seeds and unopened banks.
- **What would discriminate the hypotheses:**
  - A large spread across configurations supports hypothesis 1.
  - A flat spread with still-rising training curves points to hypothesis 2, and the follow-up
    becomes the duration experiment.
  - A flat spread with flat curves points to hypotheses 3–5, reward, exposure and representation.
- **Evaluation:** the protocol stays as it is. Death time is not recorded in evaluation files today.
  Recording it would be a versioned protocol change, which Codex would need to specify.

This does not fit before 08:00, so nothing is launched.
