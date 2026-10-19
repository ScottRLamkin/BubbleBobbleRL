# Running your own experiments

Everything here is one command each, runs unattended, and leaves its results
under `runs/`. A full "round" is: train one or more agents, score them on
the same fresh seeds, profile what they do, and watch the interesting ones.

## Setup, once

```bash
uv sync --extra play --extra train
```

Two habits that matter when several runs share the machine:

- `export OMP_NUM_THREADS=1` before launching. Each run then uses one core;
  without it every run grabs all 12 and they crawl.
- `caffeinate -is` in front of the first run keeps the Mac awake (lid open,
  plugged in). Everything else can go on in the background with `&`.

## 1. Train

```bash
export OMP_NUM_THREADS=1
caffeinate -is uv run python scripts/train_ppo.py \
    --levels 1-100 --time-penalty 0.01 --death-penalty 5 \
    --total-steps 100000000 --seed 1 \
    --run-name my_first_run --quiet \
    > runs/my_first_run.log 2>&1 &
```

Speed is about 14,000 agent steps per second per run, so 100M steps is
roughly two hours. The model lands at `runs/my_first_run/model.pt`
(saved continuously, so you can score a run before it finishes), and the
log prints the average return of the last 20 episodes once per million steps:

```bash
tail -3 runs/my_first_run.log
```

### Curves: MLflow (and TensorBoard)

Every run logs to a local MLflow store (`mlflow.db` in the repo, SQLite,
nothing leaves the machine) and to TensorBoard files in its run directory.
To browse runs, compare them and look at the curves:

```bash
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db
```

then open http://127.0.0.1:5000. Each run records all its flags as
parameters, the final `model.pt` as an artifact, and these metrics every
5 PPO updates (`--log-every` changes that):

| Metric | What to look for |
|---|---|
| `charts_episodic_return`, `charts_episodic_length` | the reward the agent is actually collecting; length tells you whether it dies fast or runs out the clock |
| `losses_policy_loss` | PPO's surrogate objective; small and noisy is normal, it is not meant to go to zero |
| `losses_value_loss` | how well the critic predicts return; should fall, then track the reward scale |
| `losses_entropy` | how random the policy is; falling means it is committing to actions, collapsing to ~0 means it stopped exploring |
| `losses_approx_kl`, `losses_clipfrac` | how far each update moves the policy; KL above ~0.02 or clipfrac above ~0.3 means the learning rate is too high |
| `losses_explained_variance` | 1 = the critic explains the returns perfectly, 0 = no better than a constant, negative = worse |
| `charts_learning_rate`, `charts_level_pool`, `charts_sps` | the schedule (`--anneal-lr`, `--curriculum`) and speed |

TensorBoard shows the same curves: `uv run tensorboard --logdir runs/`.
`--no-mlflow` / `--no-tensorboard` turn either off; `evolve.py` turns both
off for its children, since 30 runs per generation is noise in the UI.

### The knobs

Reward shaping (what the agent is paid for):

| Flag | Default | What it does |
|---|---|---|
| `--time-penalty` | 0 | charge per step; 0.01 is what produced the bubble-climbing |
| `--death-penalty` | 1 | charge on death; use 5 with per-step penalties (1 makes suicide optimal, 15 makes the agent timid) |
| `--clear-bonus` | 10 | reward for clearing a level |
| `--stationary-penalty` | 0 | charge per step while x stays inside `--stationary-band` px for `--stationary-window` steps (15 steps = 1 s) |
| `--no-pop-reward` | off | stop paying for popping empty bubbles (hurt badly when tried) |

The task:

| Flag | Default | What it does |
|---|---|---|
| `--levels 1-100` | level 1 only | pool of levels, one drawn per episode; `"1,5,20-30"` works |
| `--curriculum 0.6` | off | grow the pool from level 1 to all of them over the first 60% of training |
| `--random-start` | off | player starts on a random platform |
| `--obs state|ego|screen` | state | what the agent sees: absolute positions, player-relative positions, or pixels (pixels are untested) |
| `--arch mlp|conv` | mlp | flat network, or a small CNN over the tile grid (7x slower on CPU) |

Continuing from an existing agent:

| Flag | What it does |
|---|---|
| `--init-model runs/<run>/model.pt` | start from those weights (an older, shorter observation is padded with zero weights) |

PPO itself (`--lr`, `--ent-coef`, `--clip`, `--gamma`, `--num-envs`, ...)
rarely needs touching; `--lr 1.5e-4` and lower helped slightly in the
evolution runs.

## 2. Score, on the same seeds every time

```bash
uv run python scripts/evaluate.py runs/my_first_run/model.pt --episodes 10 --seed 4242
```

Every level, 10 episodes, one life, one-minute cap: "cleared N/1000". Seed
4242 is the set every number in `docs/` uses, so your result is directly
comparable. Reference points in the current game (with projectiles):

| Agent | Cleared / 1000 |
|---|---|
| random play | about 10 |
| best camper (`runs/v6_band32_from_bouncer_50M`) | 141 |
| anything that moves | under 80 so far |

Noise: re-scoring the same model on different seeds moves it by about 15-20.
Differences smaller than that are not real. Add `--obs ego` for ego models.

## 3. See what it actually does

```bash
uv run python scripts/analyze.py runs/my_first_run/model.pt --episodes 3 --sections behaviour,outcomes
```

The behaviour profile is the quickest read: horizontal distance and x range
per episode (a camper has an x range under 10 px), share of time still,
bubble bounces per minute (3 for the old camper, 27 for the climber), and
how many episodes cross the screen. `--sections` can also include
`ablation` (which inputs it relies on), `levels` (clear rate by level
features) and `cap` (does more time help). The default runs them all and
takes about 20 minutes.

## 4. Watch it

```bash
uv run python scripts/export_levels.py runs/my_first_run/model.pt --out exports/my_first_run
open exports/my_first_run/index.html
```

A GIF per level (best of 3 tries) in a page with green/red/grey bars for
cleared/died/timed out. About 2 minutes and 30 MB. For a single level at
full speed:

```bash
uv run python scripts/train_ppo.py --play runs/my_first_run/model.pt --level 7
```

writes `agent.gif`. And to play the game yourself: `uv run bubblebobblerl-play --level 7`.

## Running a round of several at once

Four runs fit comfortably on the 8 performance cores. Put the shared flags in
an array (a plain string will not be split by zsh):

```bash
export OMP_NUM_THREADS=1
P=(--levels 1-100 --time-penalty 0.01 --death-penalty 5 --quiet)
caffeinate -is uv run python scripts/train_ppo.py "${P[@]}" --stationary-penalty 0.02 --total-steps 100000000 --seed 1 --run-name r1_still02  > runs/r1_still02.log  2>&1 &
uv run python scripts/train_ppo.py "${P[@]}" --stationary-penalty 0.05 --total-steps 100000000 --seed 2 --run-name r1_still05  > runs/r1_still05.log  2>&1 &
uv run python scripts/train_ppo.py "${P[@]}" --init-model runs/v6_band32_from_bouncer_50M/model.pt --total-steps 50000000 --seed 3 --run-name r1_bouncer_more > runs/r1_bouncer_more.log 2>&1 &
```

Then, when they are done, score them all with one loop:

```bash
for r in r1_still02 r1_still05 r1_bouncer_more; do
  uv run python scripts/evaluate.py runs/$r/model.pt --episodes 10 --seed 4242 &
done; wait
```

Do not edit `scripts/` or `src/` while runs are going: a run that imports a
module late (the evolution workers do) can pick up a half-changed codebase.

## Letting evolution do the rounds

`scripts/evolve.py` automates "train a population, keep the best, reseed":

```bash
caffeinate -is uv run python scripts/evolve.py \
    --base runs/v6_band32_from_bouncer_50M/model.pt --name myevo \
    --generations 3 --population 30 --survivors 10 --steps 10000000 --workers 8
```

Each generation mutates twelve settings (reward shaping and PPO
hyperparameters), fine-tunes 30 children in parallel, scores everyone on the
same seeds, and keeps the top 10. About an hour per generation;
`runs/evolve/myevo/leaderboard.md` has the ranked table and re-running the
same command resumes after a crash. The genome it mutates and the
hand-picked first-generation variants are at the top of the script if you
want to change what it searches over.

Every child becomes an MLflow run in experiment `evolve-myevo` (curves,
genome, evaluation, `survived` tag) and each generation adds a summary run.
While it runs, the server it starts serves http://127.0.0.1:5001; afterwards
the usual `mlflow ui` command shows the same runs. One lesson from `evo10`:
fine-tuning from a trained agent wants a learning rate of about 5e-5 to
1e-4, not the 2.5e-4 default, or the first few million steps undo it.

## Ideas that have not been tried

- A stationary penalty of 0.02-0.05 with death penalty 5: forces movement,
  probably at the cost of the climbing and the clear rate. Worth seeing.
- Paying for distance covered instead of charging for standing still (a few
  lines in `BubbleBobbleEnv.step`, next to `stationary_penalty`).
- A pool of 10 levels instead of 100, to find out whether a moving agent can
  be learned at all on fewer layouts.
- Longer runs: nothing here went past 200M steps.
- Recording your own play in `play.py` and pretraining from it (the most
  likely route to a moving agent that survives, in my view).

## Where things live

| Path | Contents |
|---|---|
| `runs/<name>/model.pt`, `runs/<name>.log` | each run's weights and progress (gitignored) |
| `runs/analysis/` | JSON and Markdown from `analyze.py` |
| `mlflow.db`, `mlruns/` | MLflow's run database and artifacts (gitignored) |
| `exports/<name>/index.html` | galleries (gitignored) |
| `docs/*.md`, `docs/report.html` | the write-ups; `uv run python scripts/build_report.py` rebuilds the report |
