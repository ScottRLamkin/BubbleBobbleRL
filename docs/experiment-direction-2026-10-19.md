# Experiment direction and tracking requirements — October 19, 2026

User-directed requirements for the next implementation. This document replaces
the proposed restriction of architecture testing to a later, diagnosed limitation.
It does not modify completed campaigns or authorize a new training launch.
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
Exact campaign cost, seeds, acceptance rules and dispatch remain a separate
pre-launch specification; the proposed widths are not a launched search.

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
