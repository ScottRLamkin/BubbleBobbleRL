# Repository instructions for agents

Before proposing or changing RL training, evolutionary search, evaluation, or
training campaigns, read [the October 18 training review](docs/training-review-2026-10-18.md).
This applies to Fable and other agents working in this repository.

- Address the review's findings in proposed experiments. State which defect or
  hypothesis each experiment investigates and what evidence would support or
  reject it. Recheck dated findings against the current implementation.
- Define a compute budget, comparison baseline, success metric, and stopping
  criterion before launching a training campaign. State whether the budget is
  elapsed time on specified CPU hardware or aggregate CPU core-hours, and whether
  evaluation is included.
- Treat useful competence after approximately one hour of CPU training as the
  user's engineering target, not an established performance guarantee. Define
  competence explicitly for each experiment.
- Distinguish improvements in reward, checkpoint selection, and level-clear
  performance from changes in learned behavior. Preserve evidence sufficient to
  make those comparisons.

The review is a handoff for investigation and improvement. Reading it does not
authorize stopping active runs or automatically changing their training settings.

For the October 18–19 overnight collaboration, read and follow
[the shared Fable–Codex progress log](docs/fable-codex-progress.md). Fable should
append evidence and questions there at milestones and at least every 30 minutes
while working; Codex will append review notes during its scheduled checks. Read
the latest entries before writing, append without replacing anyone else's work,
and acknowledge feedback by entry ID. This file is communication, not a scheduler.
