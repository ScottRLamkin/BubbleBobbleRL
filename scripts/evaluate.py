"""Score a trained model the same way regardless of how it was trained.

    uv run python scripts/evaluate.py runs/<run>/model.pt

Plays every level in --levels for --episodes episodes each (1 life, sampled
actions, fixed seeds) and counts how each episode ended. This is the fitness
measure used by evolve.py: it ignores the reward the model was trained on.
"""

from __future__ import annotations

import argparse

import gymnasium as gym
import numpy as np

import bubblebobblerl  # noqa: F401  (registers BubbleBobble-v0)

try:
    import torch
except ImportError:
    raise SystemExit("torch is required: uv sync --extra train")

from train_ppo import Agent, parse_levels


STANDARD_LEVELS = "1-99"  # level 100's boss is not implemented; it never clears
STANDARD_EPISODES = 10
STANDARD_SEED = 4242


def evaluate(
    model_path: str,
    levels: list[int],
    episodes: int = STANDARD_EPISODES,
    max_steps: int = 900,
    seed: int = STANDARD_SEED,
    obs: str = "state",
    frame_skip: int = 4,
    nearest_first: bool = False,
    control_obs: bool = False,
) -> dict:
    """The standard test: every level in `levels`, `episodes` times each, one
    life, `max_steps` agent steps (900 = one minute), sampled actions. One
    env per level stepped in lockstep so the network runs batched. The
    episode cap inside the env equals the step cap, so a policy that sees
    time left sees the same clock it trained with when the caps match."""
    envs = [
        gym.make("BubbleBobble-v0", obs_type=obs, frame_skip=frame_skip, nearest_first=nearest_first,
                 control_obs=control_obs, max_episode_frames=max_steps * frame_skip)
        for _ in levels
    ]
    # Invariant: evaluation must not disturb the caller's RNG streams (the
    # trainer calls this mid-run). Model construction and action sampling use
    # their own generator / forked state; env seeding is explicit per episode.
    torch_state = torch.get_rng_state()
    np_state = np.random.get_state()
    try:
        return _evaluate(envs, model_path, levels, episodes, max_steps, seed)
    finally:
        torch.set_rng_state(torch_state)
        np.random.set_state(np_state)


def _evaluate(envs, model_path, levels, episodes, max_steps, seed) -> dict:
    agent = Agent.load(model_path, envs[0].observation_space, envs[0].action_space.n)
    # Own generator, so results do not depend on the caller's torch RNG state.
    gen = torch.Generator().manual_seed(seed)

    cleared = died = timeout = 0
    score = 0
    kills = 0
    per_level = {level: 0 for level in levels}
    per_level_outcomes = {level: [] for level in levels}
    for ep in range(episodes):
        obs_batch = []
        for env, level in zip(envs, levels):
            o, _ = env.reset(seed=seed * 100_003 + level * 101 + ep, options={"level": level})
            obs_batch.append(o)
        obs_batch = np.stack(obs_batch)
        active = np.ones(len(levels), dtype=bool)
        last_info: list[dict] = [{} for _ in levels]
        for _ in range(max_steps):
            idx = np.flatnonzero(active)
            if not len(idx):
                break
            with torch.no_grad():
                logits = agent.actor(agent._encode(torch.as_tensor(agent.obs_in(obs_batch[idx]))))
            actions = torch.multinomial(torch.softmax(logits, -1), 1, generator=gen).squeeze(1)
            for j, i in enumerate(idx):
                o, _, term, trunc, info = envs[i].step(int(actions[j]))
                obs_batch[i] = o
                last_info[i] = info
                if term or trunc:
                    active[i] = False
        for i, level in enumerate(levels):
            info = last_info[i]
            score += info["score"]
            kills += info.get("kills", 0)
            if info["enemies_alive"] == 0:
                cleared += 1
                per_level[level] += 1
                per_level_outcomes[level].append("clear")
            elif envs[i].unwrapped.game.game_over:
                died += 1
                per_level_outcomes[level].append("death")
            else:
                timeout += 1
                per_level_outcomes[level].append("timeout")
    n = len(levels) * episodes
    return {
        "episodes": n,
        "cleared": cleared,
        "died": died,
        "timeout": timeout,
        "levels_cleared": sum(1 for c in per_level.values() if c),
        "mean_score": score / n,
        "kills_per_episode": kills / n,
        "per_level": per_level_outcomes,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model")
    p.add_argument("--levels", default=STANDARD_LEVELS, help="level 100's boss is not implemented, so it is left out")
    p.add_argument("--episodes", type=int, default=STANDARD_EPISODES)
    p.add_argument("--max-steps", type=int, default=900)
    p.add_argument("--seed", type=int, default=STANDARD_SEED)
    p.add_argument("--obs", choices=["state", "ego"], default="state")
    p.add_argument("--frame-skip", type=int, default=4, help="must match the model's training")
    p.add_argument("--nearest-first", action="store_true", help="must match the model's training")
    p.add_argument("--control-obs", action="store_true", help="must match the model's training")
    p.add_argument("--per-level-out", default=None, help="write per-level outcomes to this JSON file")
    args = p.parse_args()
    import time

    t0 = time.time()
    r = evaluate(args.model, parse_levels(args.levels), args.episodes, args.max_steps, args.seed,
                 args.obs, args.frame_skip, args.nearest_first, args.control_obs)
    r["seconds"] = round(time.time() - t0, 1)
    if args.per_level_out:
        import json
        from pathlib import Path

        Path(args.per_level_out).write_text(json.dumps(r, indent=1))
    print(
        f"{args.model}: cleared {r['cleared']}/{r['episodes']} episodes "
        f"({r['levels_cleared']} levels), died {r['died']}, timed out {r['timeout']}, "
        f"mean score {r['mean_score']:.0f}, kills/episode {r['kills_per_episode']:.2f}, {r['seconds']} s"
    )


if __name__ == "__main__":
    main()
