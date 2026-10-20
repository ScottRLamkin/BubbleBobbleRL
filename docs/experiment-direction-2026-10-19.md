# Experiment direction and tracking requirements — October 19, 2026

User-directed requirements for the next implementation. This document replaces
the proposed restriction of architecture testing to a later, diagnosed limitation.
The subsequent bedtime instruction authorizes the bounded experiment round below
after the necessary tracking implementation is ready. Completed campaigns remain
unchanged.
Codex owns direction/review; Claude owns implementation/execution.

## Goal and division of responsibility

The goal is broad playing competence. ff12 is the current comparison recipe,
not an established competent player or global optimum. Insufficient model
capacity is a hypothesis to test now, not a finding.

MLflow stays enabled for training losses, learning curves and related metrics.
Use the existing local service and ordinary experiment/run organization; no
custom dashboard or MLflow replacement is needed. SQLite is the authoritative
source and history for experiment and run configurations/hyperparameters.
HTML remains useful for versioned gameplay and non-learning reports.

An experiment contains multiple runs. BOTH have their own hyperparameters.
“Fixed in this experiment” never means “hard-coded, omitted, or unchangeable.”

## SQLite record and execution contract

Use a separate application database, `experiments.sqlite3` at the repository
root, rather than editing MLflow's managed database tables. Keep it local and
gitignored, with schema migrations tracked in source.

- Experiments have stable IDs, names, questions and immutable configuration
  revisions. Each revision stores experiment hyperparameters: game/source
  identity, reference recipe, tested factors/values, shared training settings,
  seed allocation, evaluation protocol, search/sampling procedure, aggregate
  budget, concurrency, stopping, ranking and acceptance/selection rules.
- Runs have stable IDs and reference one exact experiment revision. Store their
  explicit overrides AND their complete effective hyperparameters, resolved
  before execution: architecture, observation, all reward settings, PPO and
  optimizer settings, task/exposure settings, initialization, seed, per-run
  budget and checkpoint policy. Record inherited value provenance.
- Keep parameters queryable as namespaced key/value rows with JSON-encoded
  typed values, separate experiment-parameter and run-parameter tables, and
  foreign keys to their owning records. Arrays and structured choices remain
  typed values, not flattened ambiguous strings. This allows new parameters
  without adding a database column for each option.
- Persist canonical complete configuration snapshots and hashes. JSON files
  are import/export inputs, not a competing live source of truth: dispatch
  materializes the registered immutable configuration for the existing trainer.
  Command-line changes must be resolved and registered before dispatch.
- Record changes as new experiment revisions/runs; never rewrite settings of
  already dispatched runs. Keep append-only status/change events with timestamps.
  Retry attempts retain identity and provenance rather than overwriting failure.
- Each run stores its MLflow tracking URI, experiment ID and run ID. Write
  reciprocal SQLite experiment/revision/run IDs as MLflow tags. Preserve links
  to source snapshot, checkpoint hashes, raw evaluation and gameplay artifacts.
- Evaluations are repeatable records linked to a run and exact checkpoint.
  Store their full effective protocol/hyperparameters, seed bank, metric
  definition/version and outputs. Evaluating an old policy with a new protocol
  must not rewrite its original evaluation or imply comparability.
- Use transactions, foreign keys, a busy timeout and WAL for concurrent local
  writes. Run registration must be idempotent and reject conflicting identity.

Game version is an explicit hyperparameter: store a human-readable name plus
immutable source identity/hash, not just mutable HEAD. Evaluation hyperparameters
include levels, episodes, seeds, lives, cap/units, frame skip, action sampling,
completion definition, aggregation and selection role. Preserve units and
inactive settings, including values gated by another setting.

## MLflow behavior

Remove automatic MLflow disabling from future experiment-runner commands.
Do not alter historical frozen snapshots. Preflight the configured existing
service and establish the run link before training. An unavailable tracker is
an explicit tracking problem, not permission to silently turn tracking off.
Buffer metric events durably during transient outages and synchronize to the
same run; expose pending/error state and avoid duplicate uploads on retry.

Keep learning metrics in MLflow, not a second home-grown metrics dashboard.
SQLite holds configuration, identity, lifecycle, cost summaries and artifact
references. MLflow may mirror effective hyperparameters for convenient filtering.
Its record must agree with SQLite. Basic names/tags should distinguish campaign,
arm, training seed, game version and evaluation phase.

Import the three October 19 campaigns from existing evidence, idempotently.
Link existing MLflow runs if present; otherwise create clearly labeled historical
imports with source timestamps. Missing learning curves remain missing; do not
fabricate them, rerun training to fill them, or revive withdrawn conclusions.

## What changes and what stays fixed initially

| Area | Experiment direction |
|---|---|
| Game | Use a named version accepted as reasonably playable by the user; record it. No open-ended fidelity audit before capacity testing. |
| Evaluation | Keep true completion primary initially. All protocol and metric choices are stored and configurable. |
| Network | Test capacity now: reference 256×2 MLP, with proposed branches 512×2, 512×3 and 1024×2. Record width, depth, activation, architecture and actual parameter count. |
| Observation | Start with ego plus control state; explicitly configurable and logged. |
| PPO | Start from ff12; retain all controls and their values. Numerical tuning is a separate comparison, not silently mixed into capacity changes. |
| Rewards | Preserve and log every component, weight and gating switch. Do not simplify or remove rewards as part of tracking work. |
| Exposure | Start with current uniform sampling, normal starts and no curriculum; all choices and associated settings remain configurable and recorded. |
| Other numerics | Initially retain optimizer constants, initialization, normalization and gradient clipping; record all values. |
| Budget/selection | Fresh starts and fixed endpoints initially. Duration, continuation, optimizer restoration and checkpoint selection are explicit settings for future experiments. |

Plan for a transformer architecture later: avoid schemas and checkpoint metadata
that assume all networks have only MLP width/depth. Preserve an architecture name
and architecture-specific parameters. Do not implement a transformer yet or
assume entity attention and temporal memory are the same experiment.

Capacity comparisons should report completion outcomes across training seeds,
per-level results, throughput and steps achieved under the same one-hour CPU
allowance. More capacity might help or hurt at that budget. This does not require
proving a particular behavioral defect before trying larger networks.
The overnight specification below supplies campaign cost, seeds, acceptance
rules and dispatch requirements. Authorization is not evidence of launch.

## Implementation acceptance

- Register an experiment with several runs; query both levels of hyperparameters
  and reconstruct each complete effective configuration without implicit defaults.
- Change an experiment-level evaluation setting and a run-level architecture
  setting; verify new revisions preserve old settings/results and reach the
  evaluator/trainer correctly.
- Verify full existing schema coverage, including reward gates, task exposure,
  game identity, evaluation, experiment budgets and selection/search settings.
- Verify MLflow remains on through campaign dispatch, reciprocal IDs resolve,
  and ordinary loss metrics appear. Test unavailable service and buffered replay
  without silently dropping metrics or creating duplicate runs.
- Verify concurrent registration, retry/import idempotency and configuration
  mismatch rejection with small fixture-based tests.
- Check larger MLP construction, parameter counts and save/load compatibility
  with synthetic inputs. No performance campaign is required for plumbing tests.
- Return implementation changes and validation evidence for Codex review.
  Preserve existing checkpoints, frozen sources and versioned galleries.

## Authorized overnight experiment round

The user subsequently instructed Codex to ensure experiments happen after the
tracking work, without further overnight supervision. This supersedes the
implementation-only restriction in the earlier handoff.

Claude should finish the essential SQLite/MLflow integration and its checks,
then execute this round without waiting for another human approval or a polling
tick. Historical import polish and optional presentation work must not delay
tracked new experiments. Record readiness evidence and launch in the shared
ledger; Codex reviews at 30-minute intervals.

- **Question:** does increased MLP capacity improve broad level completion
  under the same one-hour CPU allowance and current ff12 training recipe?
- **Campaign:** `capacity-1020`; new root `runs/capacity-1020`. Register its
  exact experiment revision and full run configurations in SQLite before launch.
  Freeze its machine-readable manifest and all executable source.
- **Arms:** `mlp256x2` reference, `mlp512x2`, `mlp512x3`, `mlp1024x2`.
  Inherit the complete ff12 configuration; vary only hidden width and layer
  count, plus the matched training seed. Use tanh and fresh initialization.
  No reward, observation, game-mechanics or PPO retuning during this round.
- **Game:** use the v3 game mechanics with the Baron-timer fix. Record the exact
  source identity in SQLite; verify subsequent infrastructure edits do not
  silently alter game behavior. No new fidelity campaign is a prerequisite.
- **Replication:** three fresh policies per arm, training seeds 7301–7303.
  Twelve training jobs, 60 minutes each. CPU only, one thread per job, at most
  six concurrent jobs. Record actual steps, updates, parameter count and
  elapsed allocation; larger networks need not achieve equal step counts.
- **Development evaluation:** seeds 83001/83002, all 99 levels, ten episodes
  per level, sampled actions, one life, 900 decisions at frame skip four,
  matching observation flags. Evaluate fixed endpoint checkpoints only.
  Rank larger-network arms by mean completed clears across training seeds
  and evaluation seeds; break exact ties by mean number of levels cleared
  at least once, then smaller parameter count, then arm ID.
- **Final evaluation:** freeze the selected larger-network arm, all three of
  its endpoint checkpoint hashes and all three reference hashes before opening
  seeds 93001/93002. Same evaluation protocol. Do not switch candidates or
  retune using this bank. If seed IDs collide with existing evaluation provenance,
  choose the first unused subsequent pair before launch and record the change.
  The initial IDs were checked against current campaign manifests/configs,
  not exhaustively against all historical artifacts.
- **Decision:** recommend replacement only if final mean paired improvement
  is at least 30 completions per 990 and no training-seed pair is negative.
  This is an operational threshold, not statistical significance or proof of
  broad competence. Report all pairs and per-level gains/regressions, including
  how many levels reach at least 50% observed completion, as descriptive
  coverage/reliability measures. Retain the reference if the criterion fails.
- **Budget:** maximum 15 aggregate allocated single-thread core-hours on the
  local M4 Pro, including this campaign's preflight, training, evaluation,
  retries and gallery recording. Reserve 12 hours for training, at most
  90 seconds per evaluation invocation and 15 seconds save grace per training
  job; reserve allowances before dispatch. Preflight cap ten aggregate
  core-minutes. Track MLflow service overhead separately rather than calling
  job allocations measured whole-machine CPU use.
- **Deadline:** no campaign execution after October 20, 2026 08:00
  America/Los_Angeles. Do not launch jobs that cannot fit their full reservation.
  No silent shortening or extension of an individual registered round. Fix routine setup
  problems autonomously within these limits; stop on unresolved systemic
  correctness errors. A failed/incomplete seed cannot be omitted to declare
  success. At most one infrastructure-failure retry per job, only if the
  remaining full budget and deadline allow it; no performance-based retries.
- **Tracking:** MLflow on for all training jobs, SQLite experiment/run settings
  registered, reciprocal IDs present, raw evaluations and status preserved.
  Use an exclusive runner lock, idempotent dispatch and checked subprocess
  exits. Do not create a duplicate runner during monitoring or recovery.
- **Delivery:** a results report with all arms/seeds, measured outcomes and
  allocated costs, links to SQLite identities and MLflow runs, and a newly
  dated gameplay gallery using the existing generator. Display the chosen
  larger arm and reference at the predeclared seed 7301, one unselected episode
  per level; preserve all earlier gallery versions. If budget prevents recording,
  report the missing artifact rather than exceeding the cap.

This round tests capacity under one recipe and budget, not the best achievable
larger-network policy. Transformers remain a later branch.

## Continued experiment loop until 08:00

The user's latest instruction is explicit: if experiments finish earlier, run
more experiments. This supersedes the earlier one-round restriction, 06:00
cutoff and post-completion quiet-monitoring plan. Continue designing, running
and reviewing successive bounded experiments until October 20, 2026 **08:00
America/Los_Angeles**, while a complete useful comparison still fits.

- The 15-core-hour cap above applies to the FIRST capacity round, not the whole
  night. Each following round gets its own registered budget including preflight,
  evaluations, retries and recording, at most 15 allocated core-hours per round.
  Across all rounds, at most six single-thread workers run concurrently on the
  local M4 Pro. The overall allocation ceiling is six times the remaining wall
  interval from this authorization to 08:00 (approximately 66 core-hours);
  register the exact authorization time and ceiling before subsequent dispatch.
  Sum actual costs across rounds as well as within each round.
- Codex directs subsequent questions from results through the ledger. Claude
  need not wait for the human or a monitor tick to continue a prespecified
  useful next step. The default next question is whether the best tested larger
  architecture benefits from learning-rate adaptation: compare 0.0003, 0.001
  and 0.003 at that fixed architecture, plus the currently retained reference,
  three matched fresh training seeds and one-hour endpoints. Deduplicate an
  identical candidate/reference arm. Hold other settings fixed. This tests a
  capacity/optimization question rather than declaring all larger nets bad
  from one recipe.
- After that, select a distinct, evidence-backed follow-up: a local capacity
  comparison where results suggest room, entropy/exploration tuning where
  learning diagnostics justify it, or fresh-seed replication of the strongest
  candidate when uncertainty between training seeds is the main limitation.
  Record the question and rationale before seeing that round's outcomes.
  Do not repeatedly rerun a failed acceptance test until it passes.
- Every round must register its exact arms, reference, settings, seeds, metric,
  selection rule, acceptance rule, budget and stop condition in SQLite and
  freeze a manifest before dispatch. Use the preceding round's retained
  reference, not automatically its best observed score. Reuse the first-round
  selection/acceptance protocol unless the next protocol explicitly explains
  a change before launch. Keep game version and evaluation definition stable
  for comparable rounds; no reward simplification or transformer detour.
- Fresh training and evaluation banks for each round; mark all consumed banks.
  Never retune or try another candidate on an opened final bank. Later rounds
  informed by earlier results are adaptive search, not independent confirmation
  of the whole search procedure. Report that limitation and all failed rounds.
- Reserve the complete training, evaluation and reporting allowance against
  08:00 before dispatch. Do not launch a one-hour comparison when it cannot
  finish. A shorter run would be a separately declared exploratory question,
  never mislabeled as one-hour evidence. When no useful complete experiment
  fits, finish analysis, reconciliation and report delivery through 08:00.
- Keep MLflow enabled, both levels of hyperparameters in SQLite and versioned
  gameplay available for retained improvements. Historical import/presentation
  polish must not displace feasible, useful experiments.

Codex keeps the 30-minute review loop active and performs the final assessment
at 08:00, then pauses it. Completion of one round is a trigger to plan/dispatch
the next useful round, not a reason to stop.
