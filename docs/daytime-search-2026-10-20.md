# Daytime search — October 20, 2026

Authorized by the user through **20:00 America/Los_Angeles today**. Recorded at 2026-10-20T06:48:25-07:00. This supersedes the 08:00 stop and the prior “nothing launches after replication” instruction. Codex directs experimentation; Claude implements and executes.

## Fixed design and execution

Machine-readable design: `scripts/campaigns/opt512x4_1020_design.json`; SHA256 `0d378836cb6aba99531aff0ea74d5f1ab87fc2b65bd82fb81f808834830679b6`. This is a frozen Codex research specification, not an already registered runnable Claude manifest. Preserve it; amendments require a new explicit revision before affected jobs dispatch.

- New runs: MLP **512×4**, named game and hash unchanged. Only the user may alter those locks. All other parameters are visible temporary controls or tested factors.
- Finish the active old-architecture replication intact; prepare the new program concurrently without changing live source. Start the first new batch as soon as its preflight passes and global worker slots/budget allow. No need to wait for another human approval or monitor tick.
- Twelve configurations, three matched seeds each, full 60-minute CPU endpoints. Three batches of four configurations, 12 jobs each. Same registered training seeds 7801–7803 and development banks 88001/88002 across all twelve configurations; sharing is intentional within one predeclared search.
- Every batch has its own <=15 allocated core-hour reservation, including evaluation/preflight/retries/recording. Do not repeat the reference in other batches or invent a batch-local winner/final bank. Register all twelve configurations and the whole-program selection rule before batch one starts. SQLite may use a parent design record plus batch revisions with explicit program/hash links.
- Search-only batches must finish their development evaluations and return all raw results. After all three batches, rank jointly as specified in JSON. Do not select/prune after an early batch. Minimal search-only runner adaptation may be needed; Claude owns it and should verify completion without opening final banks, global cost accounting/locking and resume without duplicates using bounded fixtures. No broad refactor.
- Freeze selected non-reference configuration, then train it and the 512×4 reference from scratch on 7901–7903 for full one-hour endpoints. Separate development 89001/89002; final 98001/98002 only after all six hashes freeze. Final evaluation does not trigger candidate switching or retuning.
- Absolute clears/attempts and percentage are primary; report all policy seeds, per-level completion/death/timeout counts, learning trajectories and actual training steps. No relative-gain headlines, +30 competence rule or unsupported plateau finding.

## Exact configurations

| Arm | Learning rate | Entropy | Clip | Epochs |
|---|---:|---:|---:|---:|
| reference_512x4 | 0.0003 | 0.0003 | 0.1 | 2 |
| opt01 | 4.8393445e-05 | 0.023148606 | 0.21818182 | 8 |
| opt02 | 6.6562567e-05 | 0.0010312591 | 0.18181818 | 8 |
| opt03 | 0.00012592649 | 0.00036557973 | 0.12727273 | 2 |
| opt04 | 0.00023823422 | 0.0029090653 | 0.16363636 | 4 |
| opt05 | 0.00045070377 | 0.00012959744 | 0.23636364 | 2 |
| opt06 | 0.00061991867 | 0.013782627 | 0.2 | 8 |
| opt07 | 3.5183822e-05 | 0.0048859195 | 0.25454545 | 4 |
| opt08 | 0.00085266461 | 0.00021766533 | 0.29090909 | 4 |
| opt09 | 9.1553211e-05 | 0.00061400929 | 0.27272727 | 2 |
| opt10 | 0.00017320508 | 0.0082061443 | 0.10909091 | 8 |
| opt11 | 0.00032767829 | 0.0017320508 | 0.14545455 | 4 |

All other effective values are in `shared_training` and the complete parameter-policy map. LR/entropy are sampled in log space, clipping linearly; epochs are discrete. These are exploratory engineering bounds, not demonstrated optima or a full causal decomposition.

## Budgets and continued experiments

- Extension allowance: **72 allocated single-thread core-hours starting 2026-10-20T06:48:25-07:00**, including the remaining tail of already-running jobs after that timestamp. Earlier overnight allocation is reported separately. This is below the six-worker remaining-wall ceiling (79.158 hours). Register the authorization event/ceiling in SQLite before new dispatch. Do not double-count old elapsed time or omit the tail.
- First program reservation: <=45 hours search plus <=8 hours confirmation = **53**; remaining extension allowance is available for Codex-directed follow-ups, with each <=15-hour batch and a full deadline reservation. MLflow service measured CPU overhead is separately reported.
- At most six single-thread jobs globally. No execution after 20:00; reserve full training, evaluation and reporting before dispatch. No silent shortened trials or performance-based retries. One infrastructure retry only if the complete allowance fits.
- After this program, Codex reviews raw outcomes and full trajectories and directs the next useful block, for example credit assignment, exposure, rewards or a local optimization follow-up. Do not stop because one program finishes or a replacement rule passes. Claude should report remaining capacity and wait only if no concrete next assignment has yet been supplied; Codex must supply it promptly at review.
- Keep the 30-minute review loop active through 20:00. At the deadline reconcile all outcomes/costs, deliver configuration/MLflow/gallery links and research limitations, and pause the automation.


## Next assigned block: discount × GAE (specified 2026-10-20T10:52:13-07:00)

Frozen conditional specification: `scripts/campaigns/credit512x4_1020_design.json`,
SHA256 `7f2a061346b7b89cc0f7c17bd395b09acf6915b652033424010856a86187c655`. Codex directs Claude to prepare this now and launch after the
current program's confirmation, subject to the existing full reservations.
This is assigned work; registration and launch have not happened yet.

| Factor | Domain | Exact tested values | Method |
|---|---|---|---|
| Discount gamma | Continuous | 0.9921875, 0.9990234375 | Horizons128/1024 decisions; crossed2×2 |
| GAE lambda | Continuous | 0.95, 0.99 | Crossed2×2 |
| Network/game | User-locked |512×4 / existing game hash | Unchanged |
| Other settings | Temporary controls | Best overall DEVELOPMENT-ranked optimizer recipe | Inherited explicitly |

Use the best of all twelve original search arms, including its reference if that
is first. Determine this only from the validated joint development ranking,
not from the current program's final bank. Freeze the next block's materialized
configs before the confirmation final bank opens. That makes this a planned
adaptive follow-up, not a response to a holdout result.

Four arms × three new matched training seeds8001–8003 × full60-minute endpoints.
Development90001/90002; freeze the selected non-reference arm and all six hashes
before final100001/100002. Same per-level test. Twelve training core-hours,
15 total including evaluation/preflight/retries/recording. Maximum six global
workers; no launch unless whole allowance fits extension72 and20:00 cutoff.

Rationale: the current optimization block leaves both credit-assignment factors
unchanged. The current source computes GAE recursion with gamma×lambda. A local
crossed comparison distinguishes the tested settings and their interaction
without changing reward/task/observation. Existing early-death outcomes do not
establish a credit-assignment defect; this tests a hypothesis. The tested values
are engineering probes, not inferred optimal bounds. All other settings remain
eligible for later experiments. No performance pruning or shortened endpoints.
