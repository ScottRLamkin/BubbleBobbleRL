# Does a lower learning rate rescue the 1024×2 MLP? — October 20, 2026 (lr-1020)

**Absolute outcome (final bank, all three training seeds pooled).**

- 1024×2 at lr 0.0003: **1,458 of 5,940 level attempts (24.5%)**. It died in 4,479 attempts and timed out in 3. 23 of 99 levels reached at least 50% observed completion, 27 were never cleared in 60 attempts, and 0 were cleared every time.
- ff12 MLP 256×2 reference: **1,554 of 5,940 level attempts (26.2%)**. It died in 4,383 attempts and timed out in 3. 22 of 99 levels reached at least 50% observed completion, 29 were never cleared in 60 attempts, and 7 were cleared every time.

Each attempt is a fresh start on one level, with one life, 900 decisions (60 simulated seconds) and sampled actions. Neither recipe is close to solving the game.

*Added 2026-10-20 06:45 at the user's instruction to report totals, not increments (CODEX-20261020T060554-0700). The paired statistics below were the registered decision rule.*

**Answer: not by the registered rule.** The best rate, 0.0003, brought 1024×2 close to the 256×2
reference but did not beat it. On the final bank the paired gains were −32, −48 and +32 clears per 990,
mean **−16.0**. The acceptance rule (mean ≥ +30 and no negative pair) is not met, so **ff12 MLP 256×2
stays the reference.**

Within this round, on the same training seeds and development bank, the learning rate mattered a great
deal for 1024×2:

| learning rate | mean development clears |
|---|---|
| 0.0003 | 250.0 |
| 0.001 (ff12's rate) | 198.2 |
| 0.003 | 0.0, all three seeds |

## Design

The round was pre-registered by `scripts/campaigns/make_lr_1020.py`, which was committed before
capacity-1020's results were known. It generated `scripts/campaigns/lr_1020.json` from capacity-1020's
frozen outcome: mlp1024x2 had been selected and the acceptance rule was not met, so ff12 256×2 was
retained. The round ran from the frozen snapshot `runs/lr-1020/snapshot` (commit `df69c19777`).

- **Question:** at the best tested larger MLP (1024×2), does the learning rate (0.0003, 0.001, 0.003)
  improve one-hour level completion relative to the retained reference (ff12 256×2)?
- **Arms:** `reference_mlp256x2`, plus `mlp1024x2_lr0.0003`, `mlp1024x2_lr0.001` and `mlp1024x2_lr0.003`.
  For the 0.001 arm, "0.001" means ff12's exact value, 0.0010000000000000002. Everything else is ff12.
- **Seeds and banks:** training seeds 7401–7403 (12 jobs), development bank 84001/84002, final bank
  94001/94002.
- **Unchanged from capacity-1020:** the evaluation protocol, the 60-minute endpoints, the selection
  rule (frozen with all six checkpoint hashes before the final bank opened), the acceptance rule and
  the 15 core-hour cap.

SQLite: experiment `exp-9b9ab42e33829c35`, revision `rev-fdca002cc996f9b5`; MLflow: http://127.0.0.1:5000 experiment `lr-1020`.

### Development bank (selection)

| arm | parameters | mean clears / 990 | mean levels cleared | per run (seed: dev seeds) |
|---|---|---|---|---|
| mlp1024x2_lr0.0003 (selected) | 1,512,458 | 250.0 | 46.5 | 7401: 253, 249; 7402: 268, 262; 7403: 244, 224 |
| mlp1024x2_lr0.001 | 1,512,458 | 198.2 | 31.2 | 7401: 169, 162; 7402: 224, 230; 7403: 202, 202 |
| mlp1024x2_lr0.003 | 1,512,458 | 0.0 | 0.0 | 7401: 0, 0; 7402: 0, 0; 7403: 0, 0 |
| reference_mlp256x2 (reference) | 181,514 | 261.5 | 44.7 | 7401: 281, 281; 7402: 302, 311; 7403: 198, 196 |

Ranking (rule: the top-ranked non-reference arm is frozen, with its three endpoint checkpoint hashes and the reference's three, before the final bank is opened; no candidate switching or retuning on the final bank): mlp1024x2_lr0.0003 > mlp1024x2_lr0.001 > mlp1024x2_lr0.003. Frozen 2026-10-20T01:29:56-07:00.

### Final bank 94001/94002 (mlp1024x2_lr0.0003 vs reference_mlp256x2)

| training seed | mlp1024x2_lr0.0003 e94001 | mlp1024x2_lr0.0003 e94002 | reference_mlp256x2 e94001 | reference_mlp256x2 e94002 | paired gain |
|---|---|---|---|---|---|
| 7401 | 251 | 246 | 278 | 283 | -32.0 |
| 7402 | 256 | 249 | 293 | 308 | -48.0 |
| 7403 | 222 | 234 | 191 | 201 | +32.0 |

Mean paired gain **-16.0** clears per 990; acceptance (mean >= 30.0, every pair >= 0.0): **not met**.

Per level, pooled over 3 training seeds x 2 final seeds (60 episodes per level): mlp1024x2_lr0.0003 gains on 35 levels and loses on 44; levels with at least 50% observed completion: mlp1024x2_lr0.0003 23, reference_mlp256x2 22.

Largest per-level differences (clears out of 60): gains L8 +25, L7 +21, L95 +20, L23 +20, L12 +17, L6 +17, L70 +13, L61 +12; losses L64 -40, L91 -28, L86 -20, L79 -19, L92 -17, L25 -15, L93 -15, L27 -14.

### Training (60-minute endpoints) and learning diagnostics

Diagnostics are MLflow means over the last 10% of each run's logged steps (training-time signals, not evaluation).

| run | steps | updates | entropy | approx KL | clip frac | expl. var. | steps/s | train clear rate | MLflow |
|---|---|---|---|---|---|---|---|---|---|
| reference_mlp256x2 s7401 | 35,913,728 | 4,384 | 0.206 | 0.0021 | 0.054 | 0.976 | 9955 | 0.278 | `9f7735fd` |
| reference_mlp256x2 s7402 | 33,923,072 | 4,141 | 0.216 | 0.0021 | 0.056 | 0.960 | 9409 | 0.330 | `64edcfba` |
| reference_mlp256x2 s7403 | 36,978,688 | 4,514 | 0.317 | 0.0023 | 0.066 | 0.977 | 10257 | 0.196 | `7246a5ce` |
| mlp1024x2_lr0.0003 s7401 | 24,936,448 | 3,044 | 0.275 | 0.0016 | 0.056 | 0.979 | 6912 | 0.253 | `9c8dfbde` |
| mlp1024x2_lr0.0003 s7402 | 23,879,680 | 2,915 | 0.274 | 0.0016 | 0.057 | 0.964 | 6620 | 0.273 | `8571017a` |
| mlp1024x2_lr0.0003 s7403 | 22,724,608 | 2,774 | 0.187 | 0.0017 | 0.050 | 0.929 | 6324 | 0.225 | `761b7380` |
| mlp1024x2_lr0.001 s7401 | 25,223,168 | 3,079 | 0.063 | 0.0025 | 0.028 | 0.986 | 6993 | 0.184 | `8d673b2d` |
| mlp1024x2_lr0.001 s7402 | 23,961,600 | 2,925 | 0.090 | 0.0037 | 0.047 | 0.970 | 6665 | 0.208 | `7dfeca4b` |
| mlp1024x2_lr0.001 s7403 | 25,362,432 | 3,096 | 0.186 | 0.0031 | 0.063 | 0.983 | 7044 | 0.195 | `b4036508` |
| mlp1024x2_lr0.003 s7401 | 24,821,760 | 3,030 | 0.000 | -0.0000 | 0.000 | 0.999 | 6884 | 0.000 | `afda5001` |
| mlp1024x2_lr0.003 s7402 | 25,206,784 | 3,077 | 0.000 | -0.0000 | 0.000 | 0.999 | 7007 | 0.000 | `3e62d4d9` |
| mlp1024x2_lr0.003 s7403 | 24,920,064 | 3,042 | 0.000 | -0.0000 | 0.000 | 0.999 | 6927 | 0.000 | `21e0cac4` |

Allocated: 12.18 single-thread core-hours of 15.0 (training, evaluation and preflight; elapsed time per job, not measured whole-machine CPU; MLflow service overhead not included).


## What this does and does not show

- **Shown:**
  - On the final bank, 1024×2 at lr 0.0003 completed a mean of 243 of 990 episodes against the
    reference's 259 (paired mean −16). It was not better by the registered margin. This design did
    not test equivalence.
  - Its per-level profile differs from the reference's: better on 35 levels, worse on 44, and at
    least 50% observed completion on 23 levels against 22.
  - Within the round, 0.0003 beat ff12's 0.001 on every training seed of the development bank. The
    development bank was also the selection bank, so this is descriptive evidence for choosing the
    next search, not an independent comparison.
- **lr 0.003:** every endpoint recorded zero clears on both development seeds. Each one has
  near-zero logged entropy at the end of training (the last 10% of logged steps averages 0.000).
  Codex verified the evaluation counts and the MLflow entropy for seed 7401, and I reported finite
  endpoint weights for that seed. The cause is unresolved. Finite endpoint weights do not exclude a
  numerical or optimisation problem during training.
- **Across rounds:** capacity-1020's 1024×2 used lr 0.001 and lost by −114.3. This round's 1024×2 at
  lr 0.0003 lost by −16.0. The two used different seeds and banks and form part of an adaptive
  search. Neither the selection nor the cross-round change identifies how much of capacity-1020's gap
  the learning rate caused.
- **Throughput is not isolated.** 1024×2 trained about 23–25M steps against the reference's 34–37M.
  The design does not separate throughput from learning dynamics.
- **Seed spread is large.** The reference ranged from 196/198 (seed 7403) to 302/311 (seed 7402) on
  the development bank. The three independent training-seed pairs showed mixed signs: the larger
  network won seed 7403 by 32. No formal uncertainty or equivalence analysis is reported, so how far
  this difference generalises is uncertain.
- **Not shown:**
  - that 1024×2 cannot beat 256×2 with further tuning (lower rates, entropy, initialisation, longer training);
  - anything about transformers;
  - statistical significance.

*Corrected 2026-10-20 02:00 after Codex review (CODEX-20261020T015102-0700): the first version said
1024×2 at lr 0.0003 "completes about as many levels", conflating levels with episodes and implying
equivalence. It also said a difference of a few tens of clears "cannot be resolved in either
direction", which was too categorical.*

## Execution notes

- **Runner:** the frozen df69c19 runner, which includes the corrected budget accounting (3e39cb2).
  Wave 2 was dispatched within 15 s of wave 1 finishing (00:29:05–00:29:19). All 12 jobs have exactly
  one attempt, with reciprocal MLflow links.
- **Review:** Codex independently re-checked the wave-1 checkpoints, the raw evaluation files and the
  SQLite records (CODEX-20261020T005102-0700).
- **Cost:**
  - 12.18 allocated single-thread core-hours from the runner;
  - plus 115 s of gallery recording, for a total of **12.21 of 15**.
  This is not measured whole-machine CPU. The MLflow service is accounted separately.

## Galleries (new, dated; earlier versions untouched)

One unselected episode per level at the predeclared seed 7401, recorded with the existing generator
from the campaign snapshot:

- reference 256×2: `exports/2026-10-20_013334-lr-1020-reference_mlp256x2-s7401-25094b33/` (32 of 99
  levels cleared in its single episodes);
- selected 1024×2 at lr 0.0003: `exports/2026-10-20_013334-lr-1020-mlp1024x2_lr0.0003-s7401-1906208c/`
  (21 of 99).

These are viewing artifacts, not performance estimates.

## Next

entropy-1020 is the pre-registered branch for an unaccepted round. It tests ent_coef 0.0001, 0.001 and
0.003 against ff12's 0.0003 at 256×2, on seeds 7501–7503 with banks 85001/85002 and 95001/95002. It
launched at 01:34:38 from snapshot `e7cc7070d8`, which carries runner 02f0cba.

## Records

- `runs/lr-1020/`: `status.json`, `events.log`, `selection.json`, `results.json`, `preflight.json`,
  raw evaluations, checkpoints.
- SQLite: `python -m exptrack show --experiment lr-1020`.
- MLflow: experiment `lr-1020`.
