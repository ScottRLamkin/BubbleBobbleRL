# Broad PPO baseline search — October 19, 2026

The user authorized implementation and execution of a real hyperparameter search,
with a result in a few hours. Previous experimental conclusions have been deleted
from the active documentation at the user's request. Do not restore them or use
them to choose bounds, exclude configurations, or explain outcomes. Reproduced
correctness defects and their regression tests remain relevant. One-hour
competence remains an engineering target.

Machine-readable authority: [frozen design](../scripts/campaigns/hyperparameter_search_1019.json).
Codex owns this design; Claude owns the execution runner and launch. Communicate
through [the shared log](fable-codex-progress.md). No competing campaigns.

## Question and design

Does a broadly screened numerical configuration produce a better reproducible
one-hour baseline than the current G recipe, under the corrected completion
metric? This addresses review critique 2 (narrow actual exploration) and critique
6 (uncontrolled selection, evidence and compute). It does not assume G's numeric
settings are good, or infer an optimum from the earlier low-rate continuation.

Use 16 fractional-factorial corners, eight stratified interior points, and two
explicit anchors. The six factors are:

| Factor | Low | High | Sampling scale |
|---|---:|---:|---|
| A: learning rate | 0.00001 | 0.001 | logarithmic |
| B: entropy coefficient | 0.0003 | 0.05 | logarithmic |
| C: discount horizon `1/(1-gamma)` | 32 decisions | 1024 decisions | logarithmic |
| D: rollout length | 64 | 512 | powers of two |
| E: PPO epochs | 2 | 8 | integer |
| F: PPO clip | 0.1 | 0.3 | linear |

The quarter fraction uses E=ABC and F=BCD, defining relation
I=ABCE=BCDF=ADEF, resolution IV. The checked design balances all main effects and
keeps them orthogonal to each other and to two-factor interactions. Main effects
remain aliased with three-factor interactions; two-factor interactions remain
aliased with each other. Do not fit an identifiable full quadratic model or claim
isolated interactions from these 16 observations. Interior points explore between
corners; they do not remove the need for independent confirmation.

The learning-rate span is 100-fold. The entropy span is approximately 167-fold.
At frame skip four, discount horizons span approximately 2.1–68.3 simulated
seconds. These are deliberately broad engineering bounds, not an assertion that
they contain the global optimum. Numeric exploration holds the observed game,
reward and architecture fixed to make this search interpretable. Spawn strategy,
reward design and architecture remain separate future questions.

Both anchors start fresh: current G parameters, and G with learning rate reduced
tenfold. G means ego observation plus control state, one-minute finite-horizon
task, explicit kill objective, 256x2 tanh MLP; all exact settings are in the JSON.
No inherited weights/optimizer, curriculum, adaptive level sampling, LR annealing,
periodic selection evaluations, or best.pt ranking. Fixed endpoint model.pt is the
policy evaluated. Corrected true level completion is primary; legacy all_killed
can be reported only as a separately labelled diagnostic.

## Execution and selection

1. **Short correctness preflight (ten core-minutes maximum):** freeze all executed
   trainer/evaluator/environment source and relevant dependency versions; record
   source and manifest hashes. Run relevant RNG-preservation, outcome-definition,
   GAE/autoreset and observation-compatibility tests. Run one tiny finite-update,
   save/load/evaluate smoke test, with no performance inference. Validate flags,
   exact design rows and fresh starts. Stop on a real failure and repair the
   identified defect; do not expand into open-ended audits. No performance run
   starts on unverified code.
2. **Screen:** 26 configurations, 15 minutes of single-thread CPU training each,
   same training seed 4100, randomized recorded order. Evaluate final weights on
   seeds 51001/51002, all 99 levels x ten episodes. Rank by mean completed clears,
   then kills, then configuration ID. Select the top two distinct configurations
   excluding anchor_G. No adaptive narrowing or pruning based on early reward.
   A short screen can disadvantage slow learners; record this limitation and do
   not turn exclusions into universal bad-configuration conclusions.
3. **One-hour comparison:** retrain the two candidates and anchor_G from scratch
   for 60 minutes each on seeds 4201/4202/4203: nine policies. All share matched
   budgets and settings. Rank candidates by mean completed clears on tuning seeds
   51001/51002, then kills, then ID. Freeze the winning configuration and six
   candidate/control checkpoint hashes before opening the final bank.
4. **Final comparison:** evaluate the frozen winner and anchor_G, each at the three
   training seeds, on fresh seeds 61001/61002. Do not use this bank for selection
   or retrying a different candidate. Report all three paired training-seed gains,
   their mean and range, per-level outcomes, kills, deaths/timeouts and actual cost.
   An engineering replacement requires mean gain at least 30 completions/990 and
   no negative paired gain. This is an operational acceptance rule, not a calibrated
   significance test. If it fails, retain G as the baseline and report no confirmed
   replacement. Do not automatically extend the search.

Competence in this campaign means reproducible completion-rate improvement under
the protocol above; it does not mean navigation across platforms has been proven.
Present confirmation performance plainly even when the acceptance rule fails.
Always publish the coverage table, failed runs and selected recipe. Do not call
failure to beat the anchor evidence that the broad region is exhausted.

## Budget and immutable execution

**18 aggregate allocated CPU core-hours total**, including evaluation/preflight,
on the local M4 Pro; at most six concurrent single-thread CPU jobs. Training
reservations are 6.5 hours for screening and nine for confirmation, leaving 2.5
hours for all other work and save grace. Evaluation hard limit: 90 seconds per
job. Training may use at most 15 seconds of save/shutdown grace, accounted for
within the total. These are allocated one-thread wall durations, not measured
CPU utilization. Periodic training evaluation is disabled; standalone evaluation
costs are included separately. Log steps/updates achieved, since settings change
throughput and the objective is performance per CPU budget.

Target elapsed duration: **3–4 hours**. Hard campaign cutoff **13:45 PDT October
19**, even though the independent review monitor lasts until 20:00. Reserve each
job's full allowance before dispatch; if insufficient budget/time remains, mark
unfinished work and report it. Do not launch a job that cannot fit. On hard timeout
use only a completed checkpoint with an accurate step/time label; do not label a
partial policy as a completed one-hour confirmation. Abort individual nonfinite
or failing runs; systemic code-integrity failures stop the campaign. No silent
substitution or retries outside the budget.

Freeze the actual Python trainer, evaluator, imported environment modules and
runner plus exact configuration. Use an immutable source snapshot with explicit
PYTHONPATH/interpreter, not merely a frozen shell wrapper pointing at live code.
Record hashes before and after execution. Avoid cached MLflow/current-directory
side effects; local campaign artifacts are sufficient. Use one runner lock,
checked subprocess exit status and an exact expected-output manifest. Save raw
per-level JSON, stdout/stderr, checkpoint hashes and atomic status after each job.
The runner must be restart-aware and never launch duplicate training. Claude may
continue independent debugging without changing frozen campaign code.

## Interpretation

The factorial portion gives exploratory main-effect contrasts over the specified
bounds under a fixed short compute budget. It is not a causal decomposition free
of higher-order interactions. Screening uses one training seed; the final three
training seeds are the independent replication unit. Evaluation episodes and
multiple checkpoints do not increase the number of trained-policy replicates.
Final-bank failure does not justify reopening it for further tuning.

Design references: [NIST on fractional-factorial aliasing](https://www.itl.nist.gov/div898/handbook/pri/section3/pri3343.htm)
and [Bergstra & Bengio on random search as a baseline](https://jmlr.org/papers/v13/bergstra12a.html).
