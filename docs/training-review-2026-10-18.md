# Training review: October 18, 2026

## Purpose and scope

The user requested a critique of the RL and evolutionary training implementation,
with particular concern that hyperparameter exploration had narrowed too early
and that compute was being spent without useful progress. Their engineering
target is a somewhat competent bot after approximately **one hour of CPU
training**. This is a target, not a demonstrated guarantee of competence across
all 99 evaluated levels. Future experiments must define competence and specify
whether their budget means elapsed CPU-only training time or aggregate core-hours.

This is a dated snapshot of the code, local MLflow experiment **11
(`evolve-wideA`)**, saved campaign results, and diagnostic evaluations inspected
on October 18. Three generations had completed; generation 4 was underway. It is
not a report on the campaign's eventual final result. No training implementation
was changed during the review.

The main assessment is that the evidence points to a training-design rut rather
than establishing insufficient hardware. That diagnosis is an interpretation;
the measurements and defects below are the supporting evidence.

## Observed results

The first three generations trained **96 children at 8 million steps each**:
**768 million additional training steps**, over approximately **157.4 minutes**
of campaign elapsed time. This excludes the substantial training history of the
starting models.

| Generation | Best newly trained child | Best unchanged starting model | Generation duration |
|---|---:|---:|---:|
| 1 | `g1m06`: 165/990 | `base0` and `base2`: 164/990 | 52.1 min |
| 2 | `g2m14`: 151/990 | `base0`: 165/990 | 50.5 min |
| 3 | `g3m07`: 170/990 | `base2`: 178/990 | 54.8 min |

Comparisons use the same evaluation seeds **within each generation**. Seeds
change between generations, so an unchanged model's rising score is not evidence
of learning. Generation 3's overall winner was an unchanged starting model.

Local evidence: `runs/evolve/wideA/state.json`,
`runs/evolve/wideA/leaderboard.md`, `runs/evolve/wideA/evolve.log`, and experiment
11 in `mlflow.db`. These are gitignored local artifacts and may not exist in a
fresh checkout; the tables here preserve the observations for that case.

A fresh evaluation used seed **92731**, levels **1–99**, **10 episodes per level**,
sampled actions, one life, frame skip 4, and the standard 900-agent-step cap:

| Model | Cleared | Died | Timed out | Levels cleared at least once |
|---|---:|---:|---:|---:|
| `runs/evolve/wideA/gen_00/base2/model.pt` | 163/990 | 463 | 364 | 25 |
| `runs/evolve/wideA/gen_03/g3m07/model.pt` | 164/990 | 527 | 299 | 28 |

That one-clear difference does not demonstrate meaningful improvement. This was
one fresh seed set, not a confidence-interval or multi-training-seed study.

A separate behavior spot check used levels **1, 7, 14, 25, 40, 60, 80, 99**, one
episode each, a 900-step cap, and the existing `analyze.run_episode` helper. The
action generator was seeded with 731; environment seeds were
`731 * 100003 + level * 101`. Horizontal ranges, in level order, were:

- `base2`: **4, 4, 0, 4, 4, 2, 4, 4 pixels**.
- `g3m07`: **0, 4, 0, 4, 4, 0, 0, 4 pixels**.

Both recorded three clears, four deaths, and one timeout. This supports continued
camping in these sampled episodes; it is not an exhaustive behavior assessment.

## Six critiques

### 1. Imported bases lose their actual training configuration

**Confirmed code defect in the continuation controls.**
[Run.load_state in evolve.py](../scripts/evolve.py) copies each base's weights but
assigns `Genome(timeout_penalty=...)` defaults instead of importing its actual
genome. A child's supposedly unmutated continuation therefore changes the recipe.

For `base2`, the source `evo10/gen_10/g10m08` genome used learning rate
approximately **0.00005197**; the imported genome uses **0.00025**, about **4.8
times higher**. Other settings also change. The source `full1013/gen_10/g10m20`
used approximately **0.00010965**, also replaced by 0.00025. Adam state is newly
initialized by `train()` as well, so these are weight-only fine-tunes rather than
exact training resumes.

**Priority:** preserve and validate each parent's real configuration. Distinguish
weight-only fine-tuning from resumption, and establish genuine continuation
controls before attributing differences to mutations. The claim that this reset
caused the plateau remains a hypothesis requiring a controlled comparison.

### 2. Advertised bounds overstate the search actually performed

**Measured coverage limitation; proposed causal interpretation.** The first 96
children explored only a small part of several nominal ranges:

| Gene | Configured bounds | Observed range in generations 1–3 |
|---|---:|---:|
| Clear bonus | 2–300 | 3.38–27.15 |
| Rollout length | 32–1024 | 55–275 |
| Entropy coefficient | 0.0005–0.1 | 0.00354–0.02442 |
| Discount gamma | 0.9–0.999 | 0.97653–0.99654 |

[mutate and plan_generation](../scripts/evolve.py) change one to four numeric
genes by factors up to three, with a separate pop-reward toggle. Every child
inherits existing policy weights. This campaign has no fresh random policies,
direct weight mutations, or protected behaviorally different lineages. With
multiple bases, the hand-picked single-base first-generation variants are also
bypassed. Architecture, observation, and control choices remain outside this
campaign's genome, even though some are exposed by the trainer.

**Priority:** compare explicit, broadly sampled configurations and fresh starts
against local fine-tuning. Consider reserving slots for different behaviors rather
than immediately eliminating every policy whose short-term clear rate is lower.
Widening bounds alone does not establish that they are being explored. It remains
a hypothesis that protecting diversity will produce a better policy here.

### 3. Observations hide state needed for reliable control

**Reproduced observation aliasing.** In [Game.step](../src/bubblebobblerl/game.py),
jump and shoot use button edges, determined by `prev_jump` and `prev_shoot`.
[BubbleBobbleEnv._obs](../src/bubblebobblerl/env.py) omits those fields, and the
current policy is feedforward. Jump state is reduced to `(p.jump & 3) / 3`, losing
the full counter that determines remaining jump duration.

Reproduction: reset a state-observation environment with seed 1, set shoot
cooldown to zero and `prev_shoot=False`, then deepcopy it and set the copy's
`prev_shoot=True`. The observations are identical. Applying action 6 (SHOOT) to
both creates one in-flight bubble in the first and none in the second; resulting
cooldowns are 11 and 0. The network cannot distinguish these states from its
current input alone.

**Priority:** expose the relevant control state, or provide observation/action
history or recurrence. Verify this with a small control diagnostic before another
large search. The reproduction establishes missing information, not the size of
its effect on final performance.

### 4. Reward and desired behavior remain misaligned

**Confirmed reward structure; hypothesized learning consequence.**
[BubbleBobbleEnv.step](../src/bubblebobblerl/env.py) pays score delta divided by
100, plus capture and clear bonuses and configured penalties. Fruit rewards span
**5–640**, compared with the default **10 for a level clear**. Empty bubble pops
and bounces can still pay reward. There is no direct term for `ev.killed`;
killing mainly pays through subsequent fruit collection, plus the last-enemy
clear bonus. Clear reward is delayed by the game's 256-frame clear countdown.

This objective can favor collecting score and repeating local behavior over
finishing levels. Disabling pops removes an early signal without necessarily
providing a sufficient replacement signal for useful combat.

**Priority:** compare an explicit kill/clear objective with bounded shaping
against the existing score-based objective. Log reward components separately.
Treat changes as controlled experiments, not as proof that a chosen reward is
correct. Potential-based shaping is a relevant reference when preserving the
underlying objective matters: [Ng, Harada, and Russell (1999)](https://people.eecs.berkeley.edu/~russell/papers/icml99-shaping.pdf).

### 5. Training and evaluation horizons disagree

**Confirmed configuration and bootstrap behavior; hypothesized learning effect.**
Training permits **four minutes**, while standard evaluation caps episodes at
**one minute**. Default gamma is 0.99 and frame skip 4 gives 15 agent decisions
per simulated second. A reward 30 seconds away receives discount weight
`0.99 ** 450`, approximately **1.1%**; at 60 seconds it is approximately **0.012%**.
Thus the four-minute timeout penalty is extremely weak as a direct incentive for
early actions under this default discount.

[train_ppo.py](../scripts/train_ppo.py) combines termination and truncation into
`next_done` and suppresses bootstrapping for both. A consistent design should
either bootstrap external time-limit truncations or define timeout as genuine
task termination and expose remaining time for a finite-horizon task. See
[Gymnasium's time-limit guidance](https://gymnasium.farama.org/main/tutorials/handling_time_limits/).

**Priority:** make the task horizon, time observation, reward timing, discount,
and bootstrap semantics consistent. Evaluate those changes before concluding
that more compute is necessary.

### 6. The campaign needs informative diagnostics and stopping criteria

**Measured runtime evidence and confirmed instrumentation limitations.** In
sampled roughly 12-minute child runs, four periodic full evaluations took about
20 seconds each, inferred from metric timestamps. Generation-end scoring took
roughly two minutes. These observations do not identify evaluation as the main
compute sink. Keeping **99 levels × 10 episodes at milestones** is reasonable;
smaller intermediate probes are an option, not a prerequisite for progress.

The campaign gives every child a fixed 8-million-step budget and runs a fixed
number of generations without a meaningful-improvement stopping criterion.
[evaluate.py](../scripts/evaluate.py) calculates per-level clears but returns only
aggregates, discarding that detail. Training rewards and best-checkpoint scores
cannot establish that navigation or combat behavior has improved. Repeatedly
selecting checkpoints on seed 4242 also makes that score a selection metric,
not an untouched final test; the generation scoring does use different seeds.

**Priority:** retain per-level outcomes and behavior diagnostics; compare to
unchanged bases on fresh evaluation seeds; define success and futility criteria
before committing compute. Track performance per elapsed time as well as steps.
Avoid promoting a selected checkpoint's score as established progress without
independent evaluation.

## Recommended next investigation

1. Restore trustworthy parent inheritance and continuation controls.
2. Resolve control-state aliasing and establish coherent horizon semantics.
3. Test combat and movement learning from scratch on a small, varied level set,
   with an explicit kill/clear objective compared against the current reward.
4. Require observable skill improvements and fresh-seed gains before expanding
   into another large all-level population search. Keep all-level milestone
   evaluation so specialist improvement is not mistaken for broad competence.

These are investigation priorities, not a completed experiment specification or
authorization to stop active runs or automatically change training. A concrete
proposal should identify its hypothesis, baseline, compute budget, success
metric, and stopping criterion. Recheck the dated findings if the implementation
has changed.
