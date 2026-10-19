# Hyperparameter census

Every hyperparameter of a training experiment, generated from `scripts/hyperparams.py`. There are no defaults: `train_ppo.py` refuses to start unless the experiment configuration states every one.

Values shown are from `configs/hparam-1019_anchor_G_screen.json`.

## Task and episode (11)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `levels` | str | "1-99" | level pool sampled at each reset, e.g. "1-99" or "1,5,20-30"; "1" = one level |
| `level_sampling` | one of uniform/hard | "uniform" | uniform, or hard: weight levels by their recent failure rate |
| `hard_sampling_weight` | float | 9.0 | hard sampling: a level's draw weight is 1 + round(weight * recent failure rate) |
| `hard_sampling_window` | int | 20 | hard sampling: recent outcomes kept per level |
| `curriculum` | float | 0.0 | grow the pool from the first level to all of it over this fraction of training (0 = off) |
| `max_episode_frames` | int | 3600 | episode cap in game frames (3600 = the standard test's one minute) |
| `frame_skip` | int | 4 | game frames per agent step |
| `lives` | int | 1 | lives per training episode |
| `random_start` | bool | false | random player start position |
| `grace_frames` | int | 0 | enemies wait this many frames before entering (training only) |
| `grace_anneal` | float | 0.0 | shrink grace_frames linearly to 0 over this fraction of training |

## Reward weights (14)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `score_reward` | bool | false | include the in-game score delta in the reward |
| `score_scale` | float | 0.01 | reward per display point of in-game score (when score_reward) |
| `pop_reward` | bool | true | with score_reward: keep the score from bare bubble pops and bounces |
| `clear_bonus` | float | 10.0 | reward when the level is completed (the game's completion event) |
| `kill_bonus` | float | 2.0 | reward per enemy killed |
| `capture_bonus` | float | 0.1 | reward per enemy captured in a bubble |
| `death_penalty` | float | 5.0 | reward lost when the player dies |
| `timeout_penalty` | float | 4.0 | reward lost when the episode clock runs out |
| `time_penalty` | float | 0.01 | reward lost per agent step |
| `stationary_penalty` | float | 0.005 | reward lost per step while x stays within stationary_band for stationary_window steps |
| `stationary_window` | int | 120 | agent steps the stationary test looks back |
| `stationary_band` | int | 32 | pixels of x movement below which the player counts as stationary |
| `explore_bonus` | float | 0.0 | reward per new x column (explore_band px wide) reached in an episode |
| `explore_band` | int | 8 | width in px of an exploration column |

## Observation (3)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `obs` | one of state/screen/ego | "ego" | observation type |
| `control_obs` | bool | true | append previous jump/shoot buttons, jump counter and time left |
| `nearest_first` | bool | false | order object slots by distance from the player |

## Return estimation (3)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `gamma` | float | 0.99 | discount per agent step |
| `gae_lambda` | float | 0.95 | GAE lambda |
| `bootstrap_truncation` | bool | false | bootstrap V at the time limit instead of treating it as terminal |

## PPO optimisation (14)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `num_envs` | int | 16 | parallel environments |
| `rollout_len` | int | 128 | agent steps per environment per update |
| `epochs` | int | 4 | passes over each rollout |
| `minibatches` | int | 4 | minibatches per epoch |
| `clip` | float | 0.1 | policy-ratio clip range |
| `ent_coef` | float | 0.01 | entropy bonus coefficient |
| `vf_coef` | float | 0.5 | value-loss coefficient |
| `norm_adv` | bool | true | normalise advantages within each minibatch |
| `max_grad_norm` | float | 0.5 | global gradient-norm clip |
| `lr` | float | 0.00025 | Adam learning rate |
| `anneal_lr` | bool | false | decay the learning rate linearly to 0 over total_steps |
| `adam_eps` | float | 1e-05 | Adam epsilon |
| `adam_beta1` | float | 0.9 | Adam beta1 |
| `adam_beta2` | float | 0.999 | Adam beta2 |

## Network (7)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `arch` | one of mlp/conv | "mlp" | encoder for state/ego observations |
| `hidden` | int | 256 | MLP width |
| `layers` | int | 2 | MLP depth |
| `act` | one of tanh/relu | "tanh" | MLP activation |
| `init_hidden_gain` | float | 1.4142135623730951 | orthogonal-init gain of hidden layers |
| `init_actor_gain` | float | 0.01 | orthogonal-init gain of the policy head |
| `init_critic_gain` | float | 1.0 | orthogonal-init gain of the value head |

## Initialisation (3)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `seed` | int | 4100 | training seed (env seeds, torch and numpy) |
| `init_model` | path or null | null | checkpoint to continue from, or null to start fresh |
| `fresh_optimizer` | bool | false | with init_model: start Adam fresh instead of loading its saved state |

## Budget (3)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `total_steps` | int | 1000000000 | agent-step budget |
| `max_minutes` | float | 0.0 | stop after this much wall time (0 = no limit) |
| `wall_minutes` | float | 15.0 | stop before an update projected to end past this much wall time (0 = no limit) |

## Checkpoint selection and periodic evaluation (4)

| hyperparameter | type | value | meaning |
|---|---|---|---|
| `eval_every` | int | 0 | agent steps between standard tests that keep best.pt (0 = off) |
| `eval_episodes` | int | 10 | episodes per level in that periodic test |
| `futility_steps` | int | 0 | stop when best.pt has not improved for this many steps (0 = off) |
| `save_every` | int | 0 | also keep a numbered snapshot every N steps (0 = off) |

Total: 62 hyperparameters.

Run controls (not hyperparameters; optional): `run_name`, `run_dir`, `experiment`, `mlflow_tag`, `log_every`, `quiet`, `no_tensorboard`, `no_mlflow`, `wall_start`.

## Evolutionary search settings (`scripts/evolve.py`)

Evolution children take every hyperparameter from the run's `--config` except the genome's genes (below), their parent model, seed and step budget. The run's own settings are required flags: `--generations`, `--population`, `--survivors`, `--steps`, `--workers`, `--eval-episodes`, `--eval-max-steps`, `--seed`. The mutation operator is hard-coded:

| gene | range | mutation |
|---|---|---|
| `clear_bonus` | 2.0 to 300.0 | log-scale |
| `time_penalty` | 0.0 to 0.1 | log-scale, floor 0.001 before scaling |
| `stationary_penalty` | 0.0 to 0.1 | log-scale, floor 0.001 before scaling |
| `stationary_band` | 8 to 64 | log-scale, rounded |
| `death_penalty` | 0.25 to 30.0 | log-scale |
| `timeout_penalty` | 0.0 to 30.0 | log-scale, floor 0.1 before scaling |
| `capture_bonus` | 0.0 to 3.0 | log-scale, floor 0.01 before scaling |
| `explore_bonus` | 0.0 to 3.0 | log-scale, floor 0.05 before scaling |
| `lr` | 1e-05 to 0.001 | log-scale |
| `ent_coef` | 0.0005 to 0.1 | log-scale |
| `clip` | 0.03 to 0.5 | log-scale |
| `gamma` | 0.9 to 0.999 | log-scale on 1 - value |
| `gae_lambda` | 0.8 to 0.99 | log-scale on 1 - value |
| `vf_coef` | 0.1 to 2.0 | log-scale |
| `epochs` | 1 to 10 | log-scale, rounded |
| `num_envs` | 4 to 64 | log-scale, rounded |
| `rollout_len` | 32 to 1024 | log-scale, rounded |
| `reward_pops` (pop_reward) | true/false | flipped with probability 0.1 |

Each child changes 1 to 4 genes, each by a factor in [1/3.0, 3.0]. Not genes (fixed by the run's config): every other hyperparameter, including `kill_bonus`, `score_reward`, `stationary_window`, the network and the observation.

## Standard-test protocol (`scripts/evaluate.py`)

Evaluation is a fixed protocol rather than an experiment choice: levels 1-99 (level 100's boss is not implemented), 10 episodes per level (990), 900 agent steps (one minute at frame skip 4), one life, sampled actions, seed 4242 unless a bank says otherwise, outcome = the game's completion event. Observation flags must match the checkpoint, which the loader enforces. Its command-line values default to this protocol.

## Fixed design (not exposed)

- Observation layout: 8 player features; slots for 16 enemies, 16 bubbles, 8 loot items, 4 in-flight bubbles, 8 enemy projectiles; the ego tile window is 11 x 15; feature scalings.
- Conv encoder layer sizes (`arch: conv` and the screen encoder).
- PPO loss form: clipped surrogate, unclipped value loss, entropy bonus; advantage normalisation epsilon 1e-8.
- Game rules, transcribed from the original Z80 source (`docs/search-correctness-audit-2026-10-19.md`).

