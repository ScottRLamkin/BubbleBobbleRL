# Does a larger MLP help at one hour? — October 19–20, 2026 (capacity-1020)

**Answer: no, not with the ff12 recipe and a fixed 60-minute CPU allowance.** Every larger network
did worse than the 256×2 reference on the development bank. The selected larger arm, 1024×2, lost
to the reference on every training seed in the final bank: paired gains −151.5, −71.5 and −120.0
clears per 990, mean **−114.3**. The acceptance rule (mean ≥ +30 and no negative pair) is not met.
**ff12 MLP 256×2 stays the reference.**

This tests capacity under one recipe and one budget. It does not show that larger networks cannot
help with a recipe tuned for them. The learning-rate round (lr-1020, running since 23:28) is the
first follow-up.

## Design

Pre-registered in `scripts/campaigns/capacity_1020.json` (the complete 48-key experiment
configuration), registered in `experiments.sqlite3` before launch, and run from the frozen snapshot
`runs/capacity-1020/snapshot` (commit `869109196a`) by `python -m exptrack campaign run`.

- **Question:** does more MLP capacity improve broad level completion under the same one-hour CPU
  allowance and the current ff12 recipe?
- **Arms:**

  | arm | network | parameters |
  |---|---|---|
  | `mlp256x2` (reference) | ff12, 256×2 | 181,514 |
  | `mlp512x2` | 512×2 | 494,090 |
  | `mlp512x3` | 512×3 | 756,746 |
  | `mlp1024x2` | 1024×2 | 1,512,458 |

  Everything else is ff12: reward, observation (ego plus control state, 441 inputs), PPO, tanh,
  fresh initialisation.
- **Game:** `2aa2548-baron-timer`, source hash `67eaeefe…`. This is the paired-1019-v3 game, Baron-timer correction included.
- **Training:**
  - seeds 7301–7303, so 12 jobs;
  - a 60-minute deadline-aware wall limit per job;
  - one thread per job, at most six at a time, on a local Apple M4 Pro.
  Larger networks were allowed fewer steps in the same time.
- **Evaluation:** all 99 levels, 10 episodes each, one life, sampled actions, 900 decisions at frame
  skip 4 (3600 frames), endpoint `model.pt`. The development bank was 83001/83002 and the final bank
  93001/93002.
- **Selection:** the larger arm with the highest mean development clears. Ties would go to mean
  levels cleared, then smaller parameter count, then arm ID. The selection was frozen with all six
  checkpoint hashes before the final bank was opened.
- **Acceptance:** mean paired gain ≥ +30 and every pair ≥ 0, on the final bank. This is an
  operational threshold, not a significance test.
- **Budget:** at most 15 single-thread core-hours, including preflight, training, evaluation and
  retries, with a cutoff of October 20 08:00.

SQLite: experiment `exp-d306503662b72eb4`, revision `rev-d3e10f3129a89c05`; MLflow: http://127.0.0.1:5000 experiment `capacity-1020`.

### Development bank (selection)

| arm | parameters | mean clears / 990 | mean levels cleared | per run (seed: dev seeds) |
|---|---|---|---|---|
| mlp1024x2 (selected) | 1,512,458 | 211.7 | 34.5 | 7301: 244, 243; 7302: 215, 196; 7303: 185, 187 |
| mlp512x2 | 494,090 | 207.2 | 35.7 | 7301: 212, 212; 7302: 249, 264; 7303: 157, 149 |
| mlp512x3 | 756,746 | 180.7 | 34.0 | 7301: 186, 186; 7302: 182, 179; 7303: 177, 174 |
| mlp256x2 (reference) | 181,514 | 316.5 | 54.0 | 7301: 368, 373; 7302: 275, 291; 7303: 292, 300 |

Ranking (rule: the top-ranked larger-network arm is frozen, with its three endpoint checkpoint hashes and the reference's three, before the final bank is opened; no candidate switching or retuning on the final bank): mlp1024x2 > mlp512x2 > mlp512x3. Frozen 2026-10-19T23:23:44-07:00.

### Final bank 93001/93002 (mlp1024x2 vs mlp256x2)

| training seed | mlp1024x2 e93001 | mlp1024x2 e93002 | mlp256x2 e93001 | mlp256x2 e93002 | paired gain |
|---|---|---|---|---|---|
| 7301 | 237 | 230 | 390 | 380 | -151.5 |
| 7302 | 211 | 228 | 293 | 289 | -71.5 |
| 7303 | 190 | 197 | 311 | 316 | -120.0 |

Mean paired gain **-114.3** clears per 990; acceptance (mean >= 30.0, every pair >= 0.0): **not met**.

Per level, pooled over 3 training seeds x 2 final seeds (60 episodes per level): mlp1024x2 gains on 9 levels and loses on 65; levels with at least 50% observed completion: mlp1024x2 20, mlp256x2 30.

Largest per-level differences (clears out of 60): gains L93 +37, L60 +20, L92 +15, L49 +13, L25 +11, L61 +9, L47 +6, L74 +3; losses L7 -45, L87 -42, L62 -30, L26 -29, L8 -28, L89 -28, L14 -27, L59 -27.

### Training (60-minute endpoints) and learning diagnostics

Diagnostics are MLflow means over the last 10% of each run's logged steps (training-time signals, not evaluation).

| run | steps | updates | entropy | approx KL | clip frac | expl. var. | steps/s | train clear rate | MLflow |
|---|---|---|---|---|---|---|---|---|---|
| mlp256x2 s7301 | 33,988,608 | 4,149 | 0.207 | 0.0023 | 0.055 | 0.957 | 9434 | 0.361 | `f28f7838` |
| mlp256x2 s7302 | 38,141,952 | 4,656 | 0.311 | 0.0025 | 0.071 | 0.968 | 10607 | 0.292 | `ad96bdc7` |
| mlp256x2 s7303 | 34,488,320 | 4,210 | 0.236 | 0.0030 | 0.069 | 0.954 | 9589 | 0.303 | `6ab57b15` |
| mlp1024x2 s7301 | 26,460,160 | 3,230 | 0.130 | 0.0039 | 0.057 | 0.977 | 7345 | 0.230 | `cfc19ebb` |
| mlp1024x2 s7302 | 25,886,720 | 3,160 | 0.161 | 0.0043 | 0.068 | 0.963 | 7198 | 0.238 | `8abd1c56` |
| mlp1024x2 s7303 | 26,861,568 | 3,279 | 0.095 | 0.0030 | 0.040 | 0.987 | 7463 | 0.174 | `e9ddb48d` |
| mlp512x2 s7301 | 33,153,024 | 4,047 | 0.134 | 0.0022 | 0.044 | 0.983 | 9186 | 0.219 | `41694a3e` |
| mlp512x2 s7302 | 32,292,864 | 3,942 | 0.113 | 0.0022 | 0.042 | 0.973 | 8984 | 0.250 | `28b1774b` |
| mlp512x2 s7303 | 32,800,768 | 4,004 | 0.204 | 0.0030 | 0.062 | 0.913 | 9112 | 0.113 | `5c97bb77` |
| mlp512x3 s7301 | 31,776,768 | 3,879 | 0.285 | 0.0047 | 0.089 | 0.966 | 8825 | 0.187 | `97aac061` |
| mlp512x3 s7302 | 32,104,448 | 3,919 | 0.264 | 0.0039 | 0.070 | 0.982 | 8913 | 0.196 | `a22afe68` |
| mlp512x3 s7303 | 29,351,936 | 3,583 | 0.102 | 0.0042 | 0.041 | 0.953 | 8158 | 0.197 | `27ba8728` |

Allocated: 12.19 single-thread core-hours of 15.0 (training, evaluation and preflight; elapsed time per job, not measured whole-machine CPU; MLflow service overhead not included).


The final bank agrees with the development bank. The reference scored 289–390 clears and 1024×2
scored 190–237, on every seed and in both banks. The reference's three seeds span 275–373 on the
development bank, a spread of about 100 clears. The gap between the reference and the best larger
arm (about 105 to 136 clears on the development bank) is as large as that spread. On the final bank
every pair is negative.

## What this does and does not show

- **Shown:** under ff12's settings and a one-hour CPU budget, MLPs of 512×2, 512×3 and 1024×2 complete
  far fewer levels than 256×2. The selected 1024×2 is worse on 65 levels and better on 9. It reaches
  at least 50% observed completion on 20 levels, against the reference's 30.
- **Step count does not explain it on its own.** 1024×2 trained about 26M steps against the
  reference's 34–38M. But 512×2 trained about 33M steps, roughly the reference's count, and still
  averaged 207 development clears against 316.
- **Training-time diagnostics** (MLflow, last 10% of each run): the larger networks ended with
  lower policy entropy. 1024×2 was at 0.10–0.16 and 512×2 at 0.11–0.20, against the reference's
  0.21–0.31. They also had higher or similar KL, and lower training clear rates. That fits the
  larger networks converging faster to narrower policies at ff12's learning rate (0.001) and entropy
  coefficient (0.0003). It is a hypothesis, not a finding.
- **Not shown:**
  - that capacity cannot help with a recipe re-tuned for it (learning rate, entropy, initialisation, longer training);
  - anything about transformers;
  - statistical significance.

  Three seed pairs show a consistent direction, not a precise effect size.
- **Behaviour versus reward:** these are level-completion results under the standard protocol, not
  training reward. Learned behaviour can be seen in the galleries below.

## Execution notes

- **Runner defect, recovered.** At 22:20 the runner's budget check counted jobs that had finished
  training but were still evaluating twice. It refused all six second-wave jobs (`not_run`, never
  dispatched) and exited without selecting or opening the final bank.
  - The fix (commit `3e39cb2`) counts each reservation once.
  - The campaign resumed at 22:22:57 from a recorded runner snapshot (`runs/capacity-1020/runner-r2`,
    `runner_snapshots.json`). It is a copy of the frozen snapshot in which only
    `scripts/exptrack/campaign.py` differs, verified file by file. Training and evaluation still
    ran the frozen snapshot's trainer, evaluator and game.
  - Effect: wave 2 started about 63 minutes after wave 1 instead of about 60.
- **Tracking.** MLflow was on for every job and nothing was left pending in the outbox. Each job's
  MLflow run carries `exptrack.*` tags, and each SQLite attempt row holds its MLflow run ID. All 24
  development and 12 final evaluations are recorded in SQLite with their full protocol. The runner
  checked that each evaluator output reported the protocol it was asked to run.
- **Cost:**
  - 12.19 allocated core-hours by the runner (preflight, training, evaluation);
  - plus 106 s of gallery recording, for a total of **12.22 of 15**.
  The MLflow service is accounted separately. Its processes used 48.5 CPU-seconds between 21:33 and
  23:29 (`runs/capacity-1020/mlflow_overhead.json`), and the first 14 minutes after launch were not
  sampled.

## Galleries (new, dated; earlier versions untouched)

One unselected episode per level at the predeclared seed 7301, recorded with the existing generator
from the campaign snapshot:

- reference 256×2: `exports/2026-10-19_232732-capacity-1020-mlp256x2-s7301-1450910b/` (34 of 99
  levels cleared in its single episodes);
- selected 1024×2: `exports/2026-10-19_232732-capacity-1020-mlp1024x2-s7301-ec521a9b/` (20 of 99).

These are viewing artifacts, not performance estimates. The catalogue is `exports/index.html`.

## Records

- `runs/capacity-1020/`: `status.json`, `events.log`, `selection.json`, `results.json`,
  `preflight.json`, raw evaluation files, checkpoints.
- SQLite: `python -m exptrack show --experiment capacity-1020`.
- MLflow: experiment `capacity-1020`. The preflight smoke runs are in `capacity-1020-preflight`.
