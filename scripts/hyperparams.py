"""Every hyperparameter of a training experiment, in one place, with no defaults.

A training run is defined by an experiment configuration (a JSON file passed
to ``train_ppo.py --config``) that states a value for EVERY hyperparameter
below; ``train_ppo`` refuses to start if one is missing or unknown. Command-line
flags may override configuration values. Nothing falls back to a built-in
default: reward weights, task settings, observation, PPO optimisation,
network, initialisation, budget and selection are all experiment choices.

    uv run python scripts/hyperparams.py --census > docs/hyperparameters.md
    uv run python scripts/hyperparams.py --check configs/hparam-1019_anchor_G.json

Run controls (output paths, logging, experiment tracking) are listed
separately: they decide where results go, not what is trained.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# (name, type, group, meaning). type: "int" | "float" | "bool" | "str" | "path?" (path or null)
# | ("choice", [...]). Names are train_ppo's argument names (dashes for underscores on the CLI).
SCHEMA: list[tuple] = [
    # --------------------------------------------------------------- task
    ("levels", "str", "task", 'level pool sampled at each reset, e.g. "1-99" or "1,5,20-30"; "1" = one level'),
    ("level_sampling", ("choice", ["uniform", "hard"]), "task",
     "uniform, or hard: weight levels by their recent failure rate"),
    ("hard_sampling_weight", "float", "task",
     "hard sampling: a level's draw weight is 1 + round(weight * recent failure rate)"),
    ("hard_sampling_window", "int", "task", "hard sampling: recent outcomes kept per level"),
    ("curriculum", "float", "task", "grow the pool from the first level to all of it over this fraction of training (0 = off)"),
    ("max_episode_frames", "int", "task", "episode cap in game frames (3600 = the standard test's one minute)"),
    ("frame_skip", "int", "task", "game frames per agent step"),
    ("lives", "int", "task", "lives per training episode"),
    ("random_start", "bool", "task", "random player start position"),
    ("grace_frames", "int", "task", "enemies wait this many frames before entering (training only)"),
    ("grace_anneal", "float", "task", "shrink grace_frames linearly to 0 over this fraction of training"),
    # ------------------------------------------------------------- reward
    ("score_reward", "bool", "reward", "include the in-game score delta in the reward"),
    ("score_scale", "float", "reward", "reward per display point of in-game score (when score_reward)"),
    ("pop_reward", "bool", "reward", "with score_reward: keep the score from bare bubble pops and bounces"),
    ("clear_bonus", "float", "reward", "reward when the level is completed (the game's completion event)"),
    ("kill_bonus", "float", "reward", "reward per enemy killed"),
    ("capture_bonus", "float", "reward", "reward per enemy captured in a bubble"),
    ("death_penalty", "float", "reward", "reward lost when the player dies"),
    ("timeout_penalty", "float", "reward", "reward lost when the episode clock runs out"),
    ("time_penalty", "float", "reward", "reward lost per agent step"),
    ("stationary_penalty", "float", "reward", "reward lost per step while x stays within stationary_band for stationary_window steps"),
    ("stationary_window", "int", "reward", "agent steps the stationary test looks back"),
    ("stationary_band", "int", "reward", "pixels of x movement below which the player counts as stationary"),
    ("explore_bonus", "float", "reward", "reward per new x column (explore_band px wide) reached in an episode"),
    ("explore_band", "int", "reward", "width in px of an exploration column"),
    # -------------------------------------------------------- observation
    ("obs", ("choice", ["state", "screen", "ego"]), "observation", "observation type"),
    ("control_obs", "bool", "observation", "append previous jump/shoot buttons, jump counter and time left"),
    ("nearest_first", "bool", "observation", "order object slots by distance from the player"),
    # ------------------------------------------------------------- return
    ("gamma", "float", "return", "discount per agent step"),
    ("gae_lambda", "float", "return", "GAE lambda"),
    ("bootstrap_truncation", "bool", "return", "bootstrap V at the time limit instead of treating it as terminal"),
    # --------------------------------------------------------------- PPO
    ("num_envs", "int", "ppo", "parallel environments"),
    ("rollout_len", "int", "ppo", "agent steps per environment per update"),
    ("epochs", "int", "ppo", "passes over each rollout"),
    ("minibatches", "int", "ppo", "minibatches per epoch"),
    ("clip", "float", "ppo", "policy-ratio clip range"),
    ("ent_coef", "float", "ppo", "entropy bonus coefficient"),
    ("vf_coef", "float", "ppo", "value-loss coefficient"),
    ("norm_adv", "bool", "ppo", "normalise advantages within each minibatch"),
    ("max_grad_norm", "float", "ppo", "global gradient-norm clip"),
    ("lr", "float", "ppo", "Adam learning rate"),
    ("anneal_lr", "bool", "ppo", "decay the learning rate linearly to 0 over total_steps"),
    ("adam_eps", "float", "ppo", "Adam epsilon"),
    ("adam_beta1", "float", "ppo", "Adam beta1"),
    ("adam_beta2", "float", "ppo", "Adam beta2"),
    # ----------------------------------------------------------- network
    ("arch", ("choice", ["mlp", "conv"]), "network", "encoder for state/ego observations"),
    ("hidden", "int", "network", "MLP width"),
    ("layers", "int", "network", "MLP depth"),
    ("act", ("choice", ["tanh", "relu"]), "network", "MLP activation"),
    ("init_hidden_gain", "float", "network", "orthogonal-init gain of hidden layers"),
    ("init_actor_gain", "float", "network", "orthogonal-init gain of the policy head"),
    ("init_critic_gain", "float", "network", "orthogonal-init gain of the value head"),
    # ---------------------------------------------------- initialisation
    ("seed", "int", "init", "training seed (env seeds, torch and numpy)"),
    ("init_model", "path?", "init", "checkpoint to continue from, or null to start fresh"),
    ("fresh_optimizer", "bool", "init", "with init_model: start Adam fresh instead of loading its saved state"),
    # ------------------------------------------------------------ budget
    ("total_steps", "int", "budget", "agent-step budget"),
    ("max_minutes", "float", "budget", "stop after this much wall time (0 = no limit)"),
    ("wall_minutes", "float", "budget", "stop before an update projected to end past this much wall time (0 = no limit)"),
    # --------------------------------------------- selection and evaluation
    ("eval_every", "int", "selection", "agent steps between standard tests that keep best.pt (0 = off)"),
    ("eval_episodes", "int", "selection", "episodes per level in that periodic test"),
    ("futility_steps", "int", "selection", "stop when best.pt has not improved for this many steps (0 = off)"),
    ("save_every", "int", "selection", "also keep a numbered snapshot every N steps (0 = off)"),
]

# Not hyperparameters: where results go and how they are logged. Optional.
# MLflow tracking is mandatory, so there is deliberately no control to disable it.
RUN_CONTROLS = ("run_name", "run_dir", "experiment", "mlflow_tag", "log_every", "quiet", "no_tensorboard",
                "wall_start", "mlflow_tracking_uri", "mlflow_run_id", "metric_outbox")

NAMES = [s[0] for s in SCHEMA]
GROUPS = {"task": "Task and episode", "reward": "Reward weights", "observation": "Observation",
          "return": "Return estimation", "ppo": "PPO optimisation", "network": "Network",
          "init": "Initialisation", "budget": "Budget", "selection": "Checkpoint selection and periodic evaluation"}

# Values that were hard-coded, or carried other names, before 2026-10-19. Used ONLY
# to read the config.json of a run trained before that date (provenance, continuation,
# evolution), never to fill a new experiment.
LEGACY_IMPLICIT = {
    "score_scale": 0.01, "explore_band": 8, "hard_sampling_weight": 9.0, "hard_sampling_window": 20,
    "norm_adv": True, "max_grad_norm": 0.5, "adam_eps": 1e-5, "adam_beta1": 0.9, "adam_beta2": 0.999,
    "init_hidden_gain": math.sqrt(2), "init_actor_gain": 0.01, "init_critic_gain": 1.0,
}
LEGACY_RENAMES = {"no_score_reward": ("score_reward", lambda v: not v), "no_pop_reward": ("pop_reward", lambda v: not v)}


def kind(name):
    for s in SCHEMA:
        if s[0] == name:
            return s[1]
    raise KeyError(name)


def coerce(name, value):
    """Type-check one value; returns the coerced value or raises ValueError."""
    t = kind(name)
    if isinstance(t, tuple):
        if value not in t[1]:
            raise ValueError(f"{name}: {value!r} not one of {t[1]}")
        return value
    if t == "path?":
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name}: expected a path or null, got {value!r}")
        return value
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ValueError(f"{name}: expected true or false, got {value!r}")
    if t == "int":
        if isinstance(value, bool) or not float(value).is_integer():
            raise ValueError(f"{name}: expected an integer, got {value!r}")
        return int(value)
    if t == "float":
        if isinstance(value, bool):
            raise ValueError(f"{name}: expected a number, got {value!r}")
        return float(value)
    if t == "str":
        if not isinstance(value, str):
            raise ValueError(f"{name}: expected a string, got {value!r}")
        return value
    raise AssertionError(t)


def validate(cfg: dict) -> dict:
    """A complete experiment: every hyperparameter present, none unknown, all typed."""
    missing = [n for n in NAMES if n not in cfg]
    unknown = [k for k in cfg if k not in NAMES and k not in RUN_CONTROLS]
    if missing or unknown:
        raise ValueError("incomplete experiment configuration:"
                         + (f" missing {missing}" if missing else "") + (f" unknown {unknown}" if unknown else ""))
    return {k: (coerce(k, v) if k in NAMES else v) for k, v in cfg.items()}


def from_legacy_run(config: dict) -> dict:
    """Hyperparameters of a run trained before 2026-10-19, from its config.json
    (which recorded every argument the trainer had then), with the values that
    were hard-coded at the time made explicit. Raises if anything else is missing."""
    out = {}
    for k, v in config.items():
        if k in LEGACY_RENAMES:
            new, f = LEGACY_RENAMES[k]
            out[new] = f(v)
        elif k in NAMES:
            out[k] = v
    if not out.get("levels"):  # single-level runs recorded "level" with levels null
        out["levels"] = str(config.get("level", ""))
    for k, v in LEGACY_IMPLICIT.items():
        out.setdefault(k, v)
    return validate(out)


def census(config_path: str | None = None) -> str:
    base = json.loads(Path(config_path).read_text()) if config_path else {}
    lines = ["# Hyperparameter census", "",
             "Every hyperparameter of a training experiment, generated from `scripts/hyperparams.py`. There are "
             "no defaults: `train_ppo.py` refuses to start unless the experiment configuration states every one.",
             "", f"Values shown are from `{config_path}`." if config_path else "", ""]
    total = 0
    for g, title in GROUPS.items():
        rows = [s for s in SCHEMA if s[2] == g]
        total += len(rows)
        lines += [f"## {title} ({len(rows)})", "", "| hyperparameter | type | value | meaning |", "|---|---|---|---|"]
        for name, t, _, meaning in rows:
            ts = "one of " + "/".join(t[1]) if isinstance(t, tuple) else {"path?": "path or null"}.get(t, t)
            val = json.dumps(base[name]) if name in base else ""
            lines.append(f"| `{name}` | {ts} | {val} | {meaning} |")
        lines.append("")
    lines += [f"Total: {total} hyperparameters.", "",
              "Run controls (not hyperparameters; optional): " + ", ".join(f"`{r}`" for r in RUN_CONTROLS) + ".", ""]
    lines += _search_and_protocol_sections()
    return "\n".join(lines)


def _search_and_protocol_sections() -> list[str]:
    out = ["## Evolutionary search settings (`scripts/evolve.py`)", "",
           "Evolution children take every hyperparameter from the run's `--config` except the genome's genes "
           "(below), their parent model, seed and step budget. The run's own settings are required flags: "
           "`--generations`, `--population`, `--survivors`, `--steps`, `--workers`, `--eval-episodes`, "
           "`--eval-max-steps`, `--seed`. The mutation operator is hard-coded:", ""]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import evolve

        out += ["| gene | range | mutation |", "|---|---|---|"]
        for g, (lo, hi) in evolve.RANGES.items():
            how = "log-scale on 1 - value" if g in evolve.ONE_MINUS else "log-scale"
            if g in evolve.FLOORS:
                how += f", floor {evolve.FLOORS[g]} before scaling"
            if g in evolve.INT_GENES:
                how += ", rounded"
            out.append(f"| `{g}` | {lo} to {hi} | {how} |")
        out += [f"| `reward_pops` (pop_reward) | true/false | flipped with probability {evolve.POP_FLIP_PROB} |", "",
                f"Each child changes {evolve.MUTATION_GENES[0]} to {evolve.MUTATION_GENES[1]} genes, each by a factor "
                f"in [1/{evolve.MUTATION_SCALE}, {evolve.MUTATION_SCALE}]. Not genes (fixed by the run's config): "
                "every other hyperparameter, including `kill_bonus`, `score_reward`, `stationary_window`, the "
                "network and the observation.", ""]
    except Exception as e:  # noqa: BLE001
        out += [f"(evolve.py not importable here: {e})", ""]
    out += ["## Standard-test protocol (`scripts/evaluate.py`)", "",
            "Evaluation is a fixed protocol rather than an experiment choice: levels 1-99 (level 100's boss is "
            "not implemented), 10 episodes per level (990), 900 agent steps (one minute at frame skip 4), one "
            "life, sampled actions, seed 4242 unless a bank says otherwise, outcome = the game's completion "
            "event. Observation flags must match the checkpoint, which the loader enforces. Its command-line "
            "values default to this protocol.", "",
            "## Fixed design (not exposed)", "",
            "- Observation layout: 8 player features; slots for 16 enemies, 16 bubbles, 8 loot items, 4 "
            "in-flight bubbles, 8 enemy projectiles; the ego tile window is 11 x 15; feature scalings.",
            "- Conv encoder layer sizes (`arch: conv` and the screen encoder).",
            "- PPO loss form: clipped surrogate, unclipped value loss, entropy bonus; advantage normalisation "
            "epsilon 1e-8.",
            "- Game rules, transcribed from the original Z80 source (`docs/search-correctness-audit-2026-10-19.md`).",
            ""]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--census", action="store_true", help="print the census as Markdown")
    p.add_argument("--values", default=None, help="with --census: show values from this configuration")
    p.add_argument("--check", default=None, help="validate a configuration file")
    a = p.parse_args()
    if a.census:
        print(census(a.values))
    if a.check:
        validate(json.loads(Path(a.check).read_text()))
        print(f"{a.check}: complete ({len(NAMES)} hyperparameters)")
    if not (a.census or a.check):
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
