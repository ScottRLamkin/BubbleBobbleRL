# BubbleBobbleRL

A Gymnasium environment for DWedit's TI-83 calculator port of Bubble Bobble,
reimplemented in Python with the open-sourced Z80 code as the spec, plus the
scripts used to train and study agents on it.

The original game, its source (`bub_*.z80`) and documentation are kept under
`src/bubblebobblerl/bubble/`. The reimplementation covers all 100 levels, the
eight enemy kinds and their projectiles, bubbles with air currents, fruit and
scoring; special bubbles, items, the hurry-up baron and the level-100 boss are
not implemented.

## Setup

```bash
uv sync --extra play --extra train
```

## Play it yourself

```bash
uv run bubblebobblerl-play --level 1
```

Arrows move, Up or Z jumps, Space shoots, R resets, `[` / `]` change level.

## The environment

```python
import gymnasium as gym
import bubblebobblerl  # registers BubbleBobble-v0

env = gym.make("BubbleBobble-v0", levels=list(range(1, 101)), obs_type="state")
```

Observations are either the 64x96 1-bit screen or a flat state vector; actions
are nine button combinations. See `docs/training-setup.md` for the exact
observation, reward and episode definitions.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/train_ppo.py` | Single-file PPO (`--levels 1-100`, `--arch conv`, `--random-start`, `--init-model`) |
| `scripts/evaluate.py` | Reward-independent scoring: episodes cleared over all levels |
| `scripts/evolve.py` | Resumable population-based fine-tuning |
| `scripts/export_levels.py` | GIF of an agent on every level plus an HTML gallery |
| `scripts/analyze.py` | How episodes end, observation ablations, clear rate by level feature |
| `scripts/rollout_gif.py` | Record a random or scripted policy |

## Results and write-ups

- `docs/training-setup.md`: what the agent sees and is rewarded for, all runs so far.
- `docs/model-architecture.md`: the network and the PPO update.
- `docs/analysis.md`: behaviour analysis, including why early agents learned to
  stand in a corner and what changed once enemies could shoot.
