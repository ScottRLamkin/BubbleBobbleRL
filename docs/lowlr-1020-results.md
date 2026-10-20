# Can a lower learning rate let a larger MLP beat ff12? — October 20, 2026 (lowlr-1020)

**Absolute outcome (final bank 96001/96002, all three training seeds pooled).**

- The selected 512×2 at learning rate 0.0003 completed **1,770 of 5,940 level attempts (29.8%)**.
  It died in 4,167 attempts and timed out in 3. 28 of 99 levels reached at least 50% observed
  completion, 28 levels were never cleared in 60 attempts, and 2 were cleared every time.
- The ff12 MLP 256×2 reference completed **1,569 of 5,940 (26.4%)**. It died in 4,367 attempts and
  timed out in 4. 24 of 99 levels reached at least 50%, 25 were never cleared, and 2 were cleared
  every time.

Each attempt is a fresh start on one level, with one life, 900 decisions (60 simulated seconds) and
sampled actions. This is far from solving the game: both recipes fail about 70% of level attempts,
almost always by dying.

**Registered rule.** On the same seeds the selected arm scored higher on every training-seed pair,
so the rule (mean of at least +30 per 990, no negative pair) is met. The mean is +33.5, from pairs of
+50.0, +39.5 and +11.0. That makes it the **retained recipe entering round 5**, with ff12 256×2 as the
original comparator. Passing the rule is not competent gameplay. The candidate was chosen adaptively:
it was one of three arms here, after three earlier rounds. The night's last round, `replicate-final-1020`,
is a single fresh-seed replication against ff12 on seeds 7701–7703. If it fails, the evidence conflicts
and needs review; ff12 does not come back automatically.

*Lead revised 2026-10-20 06:40 at the user's instruction to report totals, not increments
(CODEX-20261020T060554-0700).*

## Design

The round was pre-registered by `scripts/campaigns/make_round4_1020.py` (`0547864`) before
entropy-1020's results were known, and reviewed by Codex. Its branch for an unaccepted entropy-1020
generated `scripts/campaigns/lowlr_1020.json`. The round ran from the frozen snapshot
`runs/lowlr-1020/snapshot` (commit `5a2caa4fb6`), whose runner is byte-identical to `02f0cba`.

- **Question:** can a lower learning rate let a larger MLP reach or beat ff12 256×2 at one hour?
- **Rationale at registration:** in lr-1020, on the same seeds and the selection bank, 1024×2's
  development clears rose as the rate fell: 0 at 0.003, 198 at 0.001, 250 at 0.0003. The trend was
  not bracketed below 0.0003, and 512×2 had never been tried at a lower rate.
- **Arms:**
  - `reference_mlp256x2` (ff12, lr 0.001);
  - `mlp1024x2_lr0.0001`;
  - `mlp512x2_lr0.0003`;
  - `mlp1024x2_lr0.0003`.

  Everything else is ff12.
- **Seeds and banks:** training seeds 7601–7603 (12 jobs), development bank 86001/86002, final bank
  96001/96002.
- **Unchanged:** the protocol, selection rule (frozen with all six checkpoint hashes before the final
  bank opened), acceptance rule and 15 core-hour cap.

SQLite: experiment `exp-cfb605dfe16331ea`, revision `rev-e5fea8af4ef4f35e`; MLflow: http://127.0.0.1:5000 experiment `lowlr-1020`.

### Development bank (selection)

| arm | parameters | mean clears / 990 | mean levels cleared | per run (seed: dev seeds) |
|---|---|---|---|---|
| mlp512x2_lr0.0003 (selected) | 494,090 | 301.3 | 52.5 | 7601: 275, 278; 7602: 318, 330; 7603: 305, 302 |
| mlp1024x2_lr0.0001 | 1,512,458 | 265.0 | 47.3 | 7601: 238, 257; 7602: 269, 267; 7603: 284, 275 |
| mlp1024x2_lr0.0003 | 1,512,458 | 232.0 | 40.0 | 7601: 197, 199; 7602: 268, 248; 7603: 241, 239 |
| reference_mlp256x2 (reference) | 181,514 | 261.8 | 52.0 | 7601: 239, 233; 7602: 280, 269; 7603: 275, 275 |

Ranking (rule: the top-ranked non-reference arm is frozen, with its three endpoint checkpoint hashes and the reference's three, before the final bank is opened; no candidate switching or retuning on the final bank): mlp512x2_lr0.0003 > mlp1024x2_lr0.0001 > mlp1024x2_lr0.0003. Frozen 2026-10-20T05:41:38-07:00.

### Final bank 96001/96002 (mlp512x2_lr0.0003 vs reference_mlp256x2)

| training seed | mlp512x2_lr0.0003 e96001 | mlp512x2_lr0.0003 e96002 | reference_mlp256x2 e96001 | reference_mlp256x2 e96002 | paired gain |
|---|---|---|---|---|---|
| 7601 | 286 | 279 | 235 | 230 | +50.0 |
| 7602 | 302 | 326 | 271 | 278 | +39.5 |
| 7603 | 291 | 286 | 276 | 279 | +11.0 |

Mean paired gain **+33.5** clears per 990; acceptance (mean >= 30.0, every pair >= 0.0): **met**.

Per level, pooled over 3 training seeds x 2 final seeds (60 episodes per level): mlp512x2_lr0.0003 gains on 44 levels and loses on 34; levels with at least 50% observed completion: mlp512x2_lr0.0003 28, reference_mlp256x2 24.

Largest per-level differences (clears out of 60): gains L38 +41, L4 +36, L60 +34, L37 +32, L97 +31, L47 +25, L86 +19, L72 +19; losses L19 -44, L23 -38, L64 -34, L46 -21, L92 -20, L87 -18, L77 -14, L42 -12.

### Training (60-minute endpoints) and learning diagnostics

Diagnostics are MLflow means over the last 10% of each run's logged steps (training-time signals, not evaluation).

| run | steps | updates | entropy | approx KL | clip frac | expl. var. | steps/s | train clear rate | MLflow |
|---|---|---|---|---|---|---|---|---|---|
| reference_mlp256x2 s7601 | 30,973,952 | 3,781 | 0.204 | 0.0028 | 0.062 | 0.915 | 8586 | 0.227 | `d008d9cd` |
| reference_mlp256x2 s7602 | 35,438,592 | 4,326 | 0.184 | 0.0019 | 0.049 | 0.968 | 9821 | 0.276 | `6d3566ba` |
| reference_mlp256x2 s7603 | 38,223,872 | 4,666 | 0.215 | 0.0021 | 0.057 | 0.965 | 10629 | 0.302 | `2027f8d7` |
| mlp512x2_lr0.0003 s7601 | 31,940,608 | 3,899 | 0.177 | 0.0009 | 0.035 | 0.974 | 8851 | 0.273 | `921b7100` |
| mlp512x2_lr0.0003 s7602 | 32,612,352 | 3,981 | 0.358 | 0.0012 | 0.053 | 0.958 | 9077 | 0.322 | `a72505ad` |
| mlp512x2_lr0.0003 s7603 | 32,833,536 | 4,008 | 0.302 | 0.0012 | 0.051 | 0.953 | 9134 | 0.306 | `1a13ec8d` |
| mlp1024x2_lr0.0001 s7601 | 22,528,000 | 2,750 | 0.249 | 0.0005 | 0.025 | 0.944 | 6253 | 0.235 | `f4f545c4` |
| mlp1024x2_lr0.0001 s7602 | 23,707,648 | 2,894 | 0.408 | 0.0007 | 0.034 | 0.951 | 6588 | 0.263 | `2c973fe9` |
| mlp1024x2_lr0.0001 s7603 | 25,526,272 | 3,116 | 0.272 | 0.0007 | 0.029 | 0.964 | 7097 | 0.272 | `0c7cc27f` |
| mlp1024x2_lr0.0003 s7601 | 25,346,048 | 3,094 | 0.320 | 0.0021 | 0.073 | 0.970 | 7033 | 0.237 | `29f1e385` |
| mlp1024x2_lr0.0003 s7602 | 24,936,448 | 3,044 | 0.272 | 0.0015 | 0.058 | 0.949 | 6932 | 0.230 | `660b01c6` |
| mlp1024x2_lr0.0003 s7603 | 25,952,256 | 3,168 | 0.199 | 0.0010 | 0.040 | 0.979 | 7211 | 0.265 | `2fd995b5` |

Allocated: 12.18 single-thread core-hours of 15.0 (training, evaluation and preflight; elapsed time per job, not measured whole-machine CPU; MLflow service overhead not included).


## What this does and does not show

- **Shown:**
  - In this round, with ff12's other settings and one hour of CPU, 512×2 at lr 0.0003 completed more
    final-bank episodes than ff12 256×2 on every training seed: a mean of 295.0 of 990 against 261.5,
    paired mean +33.5. It was better on 44 levels and worse on 34. It reached at least 50% observed
    completion on 28 levels against 24.
  - The registered operational rule is met.
- **Not shown:**
  - that 512×2 at lr 0.0003 is generally the strongest recipe, or that its advantage holds beyond these
    seeds;
  - statistical significance.

  The margin is close to the threshold (mean +33.5 against +30; the smallest pair is +11). It is one
  round's result after adaptive selection across four rounds. The fresh-seed replication in
  `replicate-final-1020` is the pre-registered check.
- **Throughput.** The candidate trained 31.9–32.8M steps, against the reference's 31.0–38.2M. So it
  was not advantaged in steps on two of three seeds. On seed 7601 the reference trained the fewest
  steps of the round (31.0M) and scored lowest (230–239). Scheduling and behaviour-dependent
  simulation cost could both contribute to the step differences, and the design does not isolate
  them.
- **Other arms:**
  - 1024×2 at lr 0.0001 had a development mean of 265.0, close to the reference's 261.8.
  - 1024×2 at lr 0.0003 had 232.0, against 250.0 in lr-1020 on different seeds.
  - These development comparisons are selection-bank descriptions, not independent tests.
- **Across rounds:** 512×2 at ff12's rate (lr 0.001) averaged 207 development clears in capacity-1020,
  against 301 here at lr 0.0003. The seeds, banks and position in the adaptive search all differ, so
  this suggests the learning rate matters for 512×2 but does not measure how much.
- **Diagnostics** (MLflow, last 10%): the candidate's final entropy was 0.18–0.36 and its KL lower
  (about 0.001) than the reference's (about 0.002). These are descriptive and do not identify a
  mechanism.

## Execution notes

- **Runner:** the frozen 5a2caa4 runner with the 02f0cba fixes. Wave 2 was dispatched at
  04:40:51–04:41:01. All 12 jobs have exactly one attempt, with reciprocal MLflow links. No orphan,
  retry or needs-review path fired.
- **Review:** Codex verified the wave-1 checkpoints, raw evaluations, SQLite records and MLflow states
  (CODEX-20261020T052032-0700).
- **Cost:**
  - 12.18 allocated single-thread core-hours from the runner;
  - plus 104 s of gallery recording, for a total of **12.21 of 15**.
  This is not measured whole-machine CPU.

## Galleries (new, dated; earlier versions untouched)

One unselected episode per level at the predeclared seed 7601:

- selected 512×2 at lr 0.0003: `exports/2026-10-20_054503-lowlr-1020-mlp512x2_lr0.0003-s7601-cbb164c5/`
  (27 of 99 levels cleared in its single episodes);
- reference: `exports/2026-10-20_054503-lowlr-1020-reference_mlp256x2-s7601-cfafe330/` (21 of 99).

These are viewing artifacts, not performance estimates.

## Next

- **Round:** `replicate-final-1020` was generated by `make_round5_1020.py` (`c8ffaa0`, `1ac9df2`,
  `751f0c6`) after this round's outcome. It runs 512×2 at lr 0.0003 against ff12 256×2, the original
  comparator, on fresh seeds 7701–7703.
- **SQLite:** experiment `exp-2b729e1bee51657b`, revision `rev-8d049ce428f6940c`. The revision's
  parameters record `reference.retained_recipe_entering = mlp512x2_lr0.0003`,
  `reference.original_comparator = reference_mlp256x2`, and `search.consumed_banks`, which lists all
  earlier banks.
- **Launch:** 05:46:06 from snapshot `92a854de77`. Results are due about 06:52.
- **Decision:** if its rule is met on its own fresh pairs, the evidence supports the retained recipe.
  If not, the evidence conflicts and needs review.

## Records

- `runs/lowlr-1020/`: `status.json`, `events.log`, `selection.json`, `results.json`, `preflight.json`,
  raw evaluations, checkpoints.
- SQLite: `python -m exptrack show --experiment lowlr-1020`.
- MLflow: experiment `lowlr-1020`.
