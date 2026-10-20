# Does a different entropy coefficient help ff12 at one hour? — October 20, 2026 (entropy-1020)

**Absolute outcome (final bank, all three training seeds pooled).**

- 256×2 with ent_coef 0.0001: **1,658 of 5,940 level attempts (27.9%)**. It died in 4,279 attempts and timed out in 3. 25 of 99 levels reached at least 50% observed completion, 29 were never cleared in 60 attempts, and 2 were cleared every time.
- ff12 MLP 256×2 reference (ent_coef 0.0003): **1,340 of 5,940 level attempts (22.6%)**. It died in 4,600 attempts and timed out in 0. 20 of 99 levels reached at least 50% observed completion, 22 were never cleared in 60 attempts, and 0 were cleared every time.

Each attempt is a fresh start on one level, with one life, 900 decisions (60 simulated seconds) and sampled actions. Neither recipe is close to solving the game.

*Added 2026-10-20 06:45 at the user's instruction to report totals, not increments (CODEX-20261020T060554-0700). The paired statistics below were the registered decision rule.*

**Answer: suggestive but not accepted.** The selected coefficient, 0.0001, beat the 256×2 reference
(ff12's 0.0003) on two of three training seeds in the final bank. The paired gains were +118.5, −5.0
and +45.5 clears per 990, mean **+53.0**. The mean clears the +30 threshold, but the registered rule
also requires no negative pair, and seed 7502 lost by 5. **Acceptance is not met, and ff12 256×2 stays
the reference.** The candidate goes to the night's final comparison: a single fresh-seed replication,
pre-registered as round 5.

## Design

The round was pre-registered by `scripts/campaigns/make_round3_1020.py`, committed before lr-1020's
results were known and reviewed by Codex. Its branch for an unaccepted lr-1020 generated
`scripts/campaigns/entropy_1020.json`. The round ran from the frozen snapshot `runs/entropy-1020/snapshot`
(commit `e7cc7070d8`), whose runner is byte-identical to the reviewed `02f0cba` failure-path fixes.

- **Question:** at the retained reference (ff12 MLP 256×2), does a different entropy coefficient
  (0.0001, 0.001 or 0.003, against 0.0003) improve one-hour level completion?
- **Rationale at registration:** 0.0003 is the lowest value the October 19 search screened, and every
  capacity-1020 run ended with low policy entropy.
- **Arms:** `reference_mlp256x2` (ent_coef 0.0003), plus `ent0.0001`, `ent0.001` and `ent0.003`.
  Everything else is ff12.
- **Seeds and banks:** training seeds 7501–7503 (12 jobs), development bank 85001/85002, final bank
  95001/95002.
- **Unchanged:** the protocol, selection rule (frozen with all six checkpoint hashes before the final
  bank opened), acceptance rule and 15 core-hour cap.

SQLite: experiment `exp-a7f78e61fdc75b8a`, revision `rev-04950e1afbea0169`; MLflow: http://127.0.0.1:5000 experiment `entropy-1020`.

### Development bank (selection)

| arm | parameters | mean clears / 990 | mean levels cleared | per run (seed: dev seeds) |
|---|---|---|---|---|
| ent0.0001 (selected) | 181,514 | 277.3 | 47.7 | 7501: 305, 290; 7502: 292, 286; 7503: 251, 240 |
| ent0.001 | 181,514 | 274.5 | 45.7 | 7501: 286, 281; 7502: 261, 266; 7503: 276, 277 |
| ent0.003 | 181,514 | 254.3 | 47.0 | 7501: 296, 275; 7502: 232, 233; 7503: 246, 244 |
| reference_mlp256x2 (reference) | 181,514 | 227.7 | 49.5 | 7501: 186, 185; 7502: 305, 298; 7503: 194, 198 |

Ranking (rule: the top-ranked non-reference arm is frozen, with its three endpoint checkpoint hashes and the reference's three, before the final bank is opened; no candidate switching or retuning on the final bank): ent0.0001 > ent0.001 > ent0.003. Frozen 2026-10-20T03:35:54-07:00.

### Final bank 95001/95002 (ent0.0001 vs reference_mlp256x2)

| training seed | ent0.0001 e95001 | ent0.0001 e95002 | reference_mlp256x2 e95001 | reference_mlp256x2 e95002 | paired gain |
|---|---|---|---|---|---|
| 7501 | 317 | 292 | 186 | 186 | +118.5 |
| 7502 | 293 | 284 | 292 | 295 | -5.0 |
| 7503 | 239 | 233 | 181 | 200 | +45.5 |

Mean paired gain **+53.0** clears per 990; acceptance (mean >= 30.0, every pair >= 0.0): **not met**.

Per level, pooled over 3 training seeds x 2 final seeds (60 episodes per level): ent0.0001 gains on 37 levels and loses on 41; levels with at least 50% observed completion: ent0.0001 25, reference_mlp256x2 20.

Largest per-level differences (clears out of 60): gains L86 +59, L78 +56, L64 +53, L79 +50, L46 +44, L93 +39, L70 +39, L41 +34; losses L72 -35, L62 -25, L7 -24, L23 -24, L87 -23, L14 -21, L69 -20, L8 -18.

### Training (60-minute endpoints) and learning diagnostics

Diagnostics are MLflow means over the last 10% of each run's logged steps (training-time signals, not evaluation).

| run | steps | updates | entropy | approx KL | clip frac | expl. var. | steps/s | train clear rate | MLflow |
|---|---|---|---|---|---|---|---|---|---|
| reference_mlp256x2 s7501 | 31,735,808 | 3,874 | 0.186 | 0.0027 | 0.062 | 0.919 | 8805 | 0.197 | `4d6cfc52` |
| reference_mlp256x2 s7502 | 31,604,736 | 3,858 | 0.170 | 0.0021 | 0.051 | 0.949 | 8775 | 0.283 | `a4f9d9ff` |
| reference_mlp256x2 s7503 | 34,783,232 | 4,246 | 0.209 | 0.0027 | 0.064 | 0.915 | 9655 | 0.217 | `2e51da85` |
| ent0.0001 s7501 | 34,856,960 | 4,255 | 0.240 | 0.0025 | 0.063 | 0.957 | 9682 | 0.339 | `98596fc0` |
| ent0.0001 s7502 | 38,068,224 | 4,647 | 0.148 | 0.0019 | 0.043 | 0.974 | 10565 | 0.297 | `53ca1022` |
| ent0.0001 s7503 | 39,256,064 | 4,792 | 0.240 | 0.0020 | 0.060 | 0.976 | 10895 | 0.256 | `3fade19b` |
| ent0.001 s7501 | 38,486,016 | 4,698 | 0.204 | 0.0018 | 0.050 | 0.974 | 10678 | 0.289 | `4d3224a9` |
| ent0.001 s7502 | 38,354,944 | 4,682 | 0.212 | 0.0022 | 0.059 | 0.969 | 10671 | 0.263 | `b24ad649` |
| ent0.001 s7503 | 38,117,376 | 4,653 | 0.204 | 0.0021 | 0.057 | 0.971 | 10581 | 0.297 | `1f02dbc6` |
| ent0.003 s7501 | 38,199,296 | 4,663 | 0.565 | 0.0025 | 0.092 | 0.968 | 10596 | 0.293 | `63f9ada7` |
| ent0.003 s7502 | 35,299,328 | 4,309 | 0.560 | 0.0029 | 0.096 | 0.913 | 9817 | 0.239 | `74a49385` |
| ent0.003 s7503 | 40,230,912 | 4,911 | 0.432 | 0.0025 | 0.081 | 0.978 | 11187 | 0.239 | `9c70f1f0` |

Allocated: 12.17 single-thread core-hours of 15.0 (training, evaluation and preflight; elapsed time per job, not measured whole-machine CPU; MLflow service overhead not included).


## What this does and does not show

- **Shown:**
  - Every entropy candidate had a higher development mean than the reference: 277.3, 274.5 and 254.3
    against 227.7. That comparison is on the selection bank, so it is descriptive, not independent.
  - On the final bank, ent0.0001 completed a mean of 276 of 990 episodes against the reference's 223,
    a paired mean of +53.0. It won two of three seed pairs, and the third was −5.0.
  - Per level, ent0.0001 was better on 37 levels and worse on 41. It reached at least 50% observed
    completion on 25 levels against 20.
  - The registered rule was not met, so this is not an accepted improvement.
- **A throughput confound.**
  - The reference jobs trained fewer steps (31.6–34.8M) than every entropy arm (34.9–40.2M), with
    lower steps per second (8.8–9.7k against 9.7–11.2k).
  - So the reference runs completed fewer steps in the same wall-time allowance. Two possible
    contributors:
    - CPU scheduling: six single-thread jobs, the MLflow service and other processes shared
      8 performance and 4 efficiency cores, with no core pinning;
    - behaviour-dependent simulation cost: a policy's behaviour changes entity counts, episode
      lengths and resets, and the environment's work per step depends on them.
  - No scheduler measurement, controlled scheduling intervention or workload profile was made.
    This design does not isolate their contributions, or the coefficient's effect per fixed
    amount of experience.
  - The reference's step count in this round (about 32–35M) is at the low end of its range across
    rounds (32–38M).
- **Seed spread is large.** Across both banks the reference scored 185–186 on seed 7501, 181–200 on
  seed 7503 and 292–305 on seed 7502. The candidate's largest gain (+118.5) comes from a weak reference seed.
  Its one loss is on the reference's strongest seed. Three independent training-seed pairs with
  mixed signs, and no formal uncertainty analysis, leave how far this generalises uncertain.
- **Training-time diagnostics:**
  - ent_coef 0.003 ended with clearly higher entropy (0.43–0.57) than the others (0.15–0.24).
  - ent0.0001's late entropy (0.15–0.24) overlapped the reference's (0.17–0.21). That overlap is
    descriptive; it is not evidence that the coefficient has a negligible effect, nor of
    equivalence.
  - The diagnostics do not identify why ent0.0001 scored higher.
- **Not shown:**
  - that 0.0001 is better than 0.0003 in general;
  - statistical significance.

  The candidate was selected adaptively. The final bank tested it once on new seeds, and the
  registered criterion failed.

*Corrected 2026-10-20 04:30 after Codex review (CODEX-20261020T035056-0700): the first version said
ent_coef "has no plausible effect on per-step cost" and that uneven scheduling was "the likely cause"
of the step gap, which was unsupported. It also rounded the reference's per-seed ranges and treated
overlapping late entropy as showing a small effect.*

## Execution notes

- **Runner:** the frozen e7cc707 runner with the 02f0cba fixes. Wave 2 was dispatched at
  02:35:09–02:35:17. All 12 jobs have exactly one attempt, with reciprocal MLflow links. No orphan,
  retry or needs-review path was triggered.
- **Review:** Codex independently verified the wave-1 checkpoints, raw evaluations, SQLite records
  and MLflow states (CODEX-20261020T025019-0700).
- **Cost:**
  - 12.17 allocated single-thread core-hours from the runner;
  - plus 105 s of gallery recording, for a total of **12.20 of 15**.
  This is not measured whole-machine CPU. The MLflow service is accounted separately.

## Galleries (new, dated; earlier versions untouched)

One unselected episode per level at the predeclared seed 7501:

- selected ent0.0001: `exports/2026-10-20_033921-entropy-1020-ent0.0001-s7501-3124e0cc/` (35 of 99
  levels cleared in its single episodes);
- reference: `exports/2026-10-20_033921-entropy-1020-reference_mlp256x2-s7501-8a75d3c5/` (20 of 99).

These are viewing artifacts, not performance estimates. Seed 7501 is the reference's weak seed in
this round.

## Next

- **Round 4 (`lowlr-1020`),** pre-registered in `0547864` before these results and reviewed by Codex.
  It runs 1024×2 at lr 0.0001, 512×2 at 0.0003 and 1024×2 at 0.0003 against ff12 256×2, on seeds
  7601–7603. It launched at 03:40:20 from snapshot `5a2caa4fb6`.
- **Round 5 (`replicate-final-1020`),** registered in `c8ffaa0` after these results but before any
  round 4 outcome. It is a single fresh-seed replication of the strongest candidate (ent0.0001,
  unless round 4 produces a stronger one) against ff12 256×2, on seeds 7701–7703. The decision uses
  its own fresh pairs only.

## Records

- `runs/entropy-1020/`: `status.json`, `events.log`, `selection.json`, `results.json`,
  `preflight.json`, raw evaluations, checkpoints.
- SQLite: `python -m exptrack show --experiment entropy-1020`.
- MLflow: experiment `entropy-1020`.
