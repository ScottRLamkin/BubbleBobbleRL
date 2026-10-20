"""Hyperparameter schemas for experiments and runs.

Run level: every trainer hyperparameter (scripts/hyperparams.py, 62 keys) gets a
namespaced key, a unit and, where another setting switches it off, a gate. A
gated-off value is still stored (active = 0), never dropped. The network is an
architecture name plus architecture-specific parameters (network.mlp.*), so a
later architecture adds its own namespace (e.g. network.transformer.*) without
pretending every network has an MLP width and depth.

Experiment level: game identity, reference recipe, design (arms/factors),
shared training settings, seeds, evaluation protocol, search, budget,
concurrency, stopping, ranking, selection/acceptance and tracking. Every key is
required; a choice that is fixed in an experiment is still stated.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hyperparams import NAMES as TRAINER_KEYS  # noqa: E402
from hyperparams import validate as validate_trainer_config  # noqa: E402

# trainer key -> (namespaced key, unit)
RUN_KEYS: dict[str, tuple[str, str | None]] = {
    # exposure: which levels, how they are drawn, how episodes start
    "levels": ("exposure.levels", "level list"),
    "level_sampling": ("exposure.level_sampling", None),
    "hard_sampling_weight": ("exposure.hard_sampling_weight", "weight per unit failure rate"),
    "hard_sampling_window": ("exposure.hard_sampling_window", "episodes per level"),
    "curriculum": ("exposure.curriculum", "fraction of total_steps"),
    "random_start": ("exposure.random_start", None),
    "grace_frames": ("exposure.grace_frames", "game frames"),
    "grace_anneal": ("exposure.grace_anneal", "fraction of total_steps"),
    # task
    "max_episode_frames": ("task.max_episode_frames", "game frames"),
    "frame_skip": ("task.frame_skip", "game frames per decision"),
    "lives": ("task.lives", "lives"),
    # reward: every component, weight and gate
    "score_reward": ("reward.score_reward", None),
    "score_scale": ("reward.score_scale", "reward per display point"),
    "pop_reward": ("reward.pop_reward", None),
    "clear_bonus": ("reward.clear_bonus", "reward per level completion"),
    "kill_bonus": ("reward.kill_bonus", "reward per enemy killed"),
    "capture_bonus": ("reward.capture_bonus", "reward per enemy captured"),
    "death_penalty": ("reward.death_penalty", "reward lost per death"),
    "timeout_penalty": ("reward.timeout_penalty", "reward lost per timeout"),
    "time_penalty": ("reward.time_penalty", "reward lost per decision"),
    "stationary_penalty": ("reward.stationary_penalty", "reward lost per decision"),
    "stationary_window": ("reward.stationary_window", "decisions"),
    "stationary_band": ("reward.stationary_band", "pixels"),
    "explore_bonus": ("reward.explore_bonus", "reward per new column"),
    "explore_band": ("reward.explore_band", "pixels"),
    # observation
    "obs": ("observation.type", None),
    "control_obs": ("observation.control_state", None),
    "nearest_first": ("observation.nearest_first", None),
    # return estimation
    "gamma": ("return.gamma", "per decision"),
    "gae_lambda": ("return.gae_lambda", None),
    "bootstrap_truncation": ("return.bootstrap_truncation", None),
    # PPO
    "num_envs": ("ppo.num_envs", "environments"),
    "rollout_len": ("ppo.rollout_len", "decisions per environment"),
    "epochs": ("ppo.epochs", "passes per rollout"),
    "minibatches": ("ppo.minibatches", "per epoch"),
    "clip": ("ppo.clip", None),
    "ent_coef": ("ppo.ent_coef", None),
    "vf_coef": ("ppo.vf_coef", None),
    "norm_adv": ("ppo.norm_adv", None),
    "max_grad_norm": ("ppo.max_grad_norm", None),
    # optimizer
    "lr": ("optimizer.lr", None),
    "anneal_lr": ("optimizer.anneal_lr", None),
    "adam_eps": ("optimizer.adam_eps", None),
    "adam_beta1": ("optimizer.adam_beta1", None),
    "adam_beta2": ("optimizer.adam_beta2", None),
    # network: architecture name + architecture-specific parameters
    "arch": ("network.arch", None),
    "hidden": ("network.mlp.hidden", "units"),
    "layers": ("network.mlp.layers", "hidden layers"),
    "act": ("network.mlp.act", None),
    # initialisation
    "init_hidden_gain": ("init.hidden_gain", None),
    "init_actor_gain": ("init.actor_gain", None),
    "init_critic_gain": ("init.critic_gain", None),
    "seed": ("init.seed", None),
    "init_model": ("init.checkpoint", "path"),
    "fresh_optimizer": ("init.fresh_optimizer", None),
    # budget
    "total_steps": ("budget.total_steps", "decisions summed over environments"),
    "max_minutes": ("budget.max_minutes", "wall minutes (0 = none)"),
    "wall_minutes": ("budget.wall_minutes", "wall minutes (0 = none)"),
    # checkpoint policy and periodic evaluation
    "eval_every": ("checkpoint.eval_every", "decisions summed over environments (0 = off)"),
    "eval_episodes": ("checkpoint.eval_episodes", "episodes per level"),
    "futility_steps": ("checkpoint.futility_steps", "decisions summed over environments (0 = off)"),
    "save_every": ("checkpoint.save_every", "decisions summed over environments (0 = off)"),
}
assert sorted(RUN_KEYS) == sorted(TRAINER_KEYS), sorted(set(RUN_KEYS) ^ set(TRAINER_KEYS))
NAMESPACED = {ns: tk for tk, (ns, _) in RUN_KEYS.items()}


def gate(trainer_key: str, cfg: dict) -> tuple[bool, str | None]:
    """(active, governing key) for one setting given the whole configuration.
    Inactive means another setting switches it off; its value is still stored."""
    k, c = trainer_key, cfg
    if k in ("hard_sampling_weight", "hard_sampling_window"):
        return c["level_sampling"] == "hard", "exposure.level_sampling"
    if k == "grace_anneal":
        return c["grace_frames"] > 0, "exposure.grace_frames"
    if k in ("score_scale", "pop_reward"):
        return bool(c["score_reward"]), "reward.score_reward"
    if k in ("stationary_window", "stationary_band"):
        return c["stationary_penalty"] != 0, "reward.stationary_penalty"
    if k == "explore_band":
        return c["explore_bonus"] != 0, "reward.explore_bonus"
    if k in ("hidden", "layers", "act"):
        return c["arch"] == "mlp" and c["obs"] != "screen", "network.arch"
    if k in ("init_hidden_gain", "init_actor_gain", "init_critic_gain"):
        return c["init_model"] is None, "init.checkpoint"
    if k == "fresh_optimizer":
        return c["init_model"] is not None, "init.checkpoint"
    if k in ("eval_episodes", "futility_steps"):
        return c["eval_every"] > 0, "checkpoint.eval_every"
    return True, None


# --------------------------------------------------------------- experiment level
# key -> (type, unit, meaning). Types: str | int | float | bool | list | object | "str?" | "int?" | "float?"
EXPERIMENT_SCHEMA: dict[str, tuple[str, str | None, str]] = {
    "experiment.question": ("str", None, "the question the experiment answers"),
    "game.name": ("str", None, "human-readable game version name"),
    "game.source_hash": ("str", None, "sha256 of the game package files (immutable identity)"),
    "game.source_commit": ("str?", None, "git commit the game files came from"),
    "reference.name": ("str", None, "the comparison recipe"),
    "reference.config_sha256": ("str", None, "hash of the reference recipe's complete trainer configuration"),
    "design.type": ("str", None, "paired_arms | fractional_factorial_screen | grid | single"),
    "design.arms": ("object", None, "arm name -> trainer-key overrides on top of shared.training"),
    "design.factors": ("object", None, "tested factor -> values, as named in the design"),
    "design.reference_arm": ("str?", None, "the arm other arms are compared with"),
    "design.phases": ("list", None, "ordered phases; every run belongs to one (e.g. screen, confirmation)"),
    "shared.training": ("object", None, "complete trainer configuration every run starts from"),
    "seeds.training": ("object", None, "phase -> training seeds"),
    "seeds.allocation": ("str", None, "how seeds are assigned to arms"),
    "evaluation.levels": ("str", "level list", "levels in the standard test"),
    "evaluation.episodes_per_level": ("int", "episodes", "episodes per level"),
    "evaluation.seed_banks": ("object", None, "evaluation role -> seed bank"),
    "evaluation.phase_roles": ("object", None, "phase -> evaluation roles applied to its runs"),
    "evaluation.lives": ("int", "lives", "lives per evaluation episode"),
    "evaluation.max_steps": ("int", "decisions", "episode cap in decisions"),
    "evaluation.frame_skip": ("int", "game frames per decision", "frames per decision"),
    "evaluation.cap_frames": ("int", "game frames", "episode cap in game frames (max_steps x frame_skip)"),
    "evaluation.action_selection": ("str", None, "sampled | greedy"),
    "evaluation.completion_definition": ("str", None, "what counts as a clear"),
    "evaluation.metric": ("str", None, "primary metric"),
    "evaluation.metric_version": ("str", None, "version of the metric definition"),
    "evaluation.aggregation": ("str", None, "how per-seed results are combined"),
    "evaluation.checkpoint": ("str", None, "which checkpoint is evaluated"),
    "search.procedure": ("str", None, "how configurations are generated and ordered"),
    "search.order": ("list", None, "dispatch order of arms (empty = as listed)"),
    "budget.hardware": ("str", None, "machine and CPU"),
    "budget.per_run_wall_minutes": ("object", "wall minutes", "phase -> training allowance per run"),
    "budget.aggregate_core_hours": ("float", "core-hours", "cap on reserved single-thread time"),
    "budget.includes_evaluation": ("bool", None, "whether evaluation counts toward the cap"),
    "budget.max_concurrent_jobs": ("int", "jobs", "parallel jobs"),
    "budget.threads_per_job": ("int", "threads", "threads per job"),
    "budget.per_evaluation_hard_seconds": ("float", "seconds", "hard limit per standard test"),
    "budget.save_grace_seconds": ("float", "seconds", "allowed shutdown time after the training budget"),
    "budget.hard_cutoff": ("str?", "ISO time", "no job may end after this"),
    "stopping.rule": ("str", None, "when training stops"),
    "ranking.metric": ("str", None, "what runs are ranked by"),
    "ranking.tiebreak": ("list", None, "tie-break keys in order"),
    "selection.rule": ("str", None, "how a winner is chosen"),
    "acceptance.mean_paired_gain_min": ("float?", "clears per 990", "minimum mean paired gain (null = no rule)"),
    "acceptance.each_paired_gain_min": ("float?", "clears per 990", "minimum gain for every pair (null = no rule)"),
    "tracking.mlflow_uri": ("str?", None, "MLflow tracking service (null = none, historical only)"),
    "tracking.mlflow_experiment": ("str?", None, "MLflow experiment name"),
    "tracking.required": ("bool", None, "dispatch refuses to run without a working tracker"),
}

_PY = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "object": dict}


def validate_experiment(cfg: dict) -> dict:
    """Every experiment key present, none unknown, types right, and the shared
    training configuration complete (no trainer defaults anywhere)."""
    missing = [k for k in EXPERIMENT_SCHEMA if k not in cfg]
    unknown = [k for k in cfg if k not in EXPERIMENT_SCHEMA]
    if missing or unknown:
        raise ValueError("incomplete experiment configuration:" + (f" missing {missing}" if missing else "")
                         + (f" unknown {unknown}" if unknown else ""))
    for k, (t, _, _) in EXPERIMENT_SCHEMA.items():
        v = cfg[k]
        optional = t.endswith("?")
        base = t.rstrip("?")
        if v is None and optional:
            continue
        if isinstance(v, bool) and base in ("int", "float"):
            raise ValueError(f"{k}: expected {base}, got a bool")
        if not isinstance(v, _PY[base]):
            raise ValueError(f"{k}: expected {t}, got {type(v).__name__}")
    validate_trainer_config(cfg["shared.training"])
    for arm, ov in cfg["design.arms"].items():
        bad = [k for k in ov if k not in TRAINER_KEYS]
        if bad:
            raise ValueError(f"arm {arm}: unknown trainer keys {bad}")
        validate_trainer_config({**cfg["shared.training"], **ov})
    if cfg["evaluation.cap_frames"] != cfg["evaluation.max_steps"] * cfg["evaluation.frame_skip"]:
        raise ValueError("evaluation.cap_frames must equal max_steps x frame_skip")
    phases = cfg["design.phases"]
    if not phases or len(set(phases)) != len(phases):
        raise ValueError("design.phases must be a non-empty list of distinct names")
    for k in ("seeds.training", "budget.per_run_wall_minutes", "evaluation.phase_roles"):
        if set(cfg[k]) != set(phases):
            raise ValueError(f"{k} must give a value for exactly the phases {phases}")
    roles = {r for rs in cfg["evaluation.phase_roles"].values() for r in rs}
    if not roles <= set(cfg["evaluation.seed_banks"]):
        raise ValueError(f"evaluation roles {sorted(roles - set(cfg['evaluation.seed_banks']))} have no seed bank")
    ref = cfg["design.reference_arm"]
    if ref is not None and ref not in cfg["design.arms"]:
        raise ValueError(f"reference arm {ref!r} is not an arm")
    return cfg
