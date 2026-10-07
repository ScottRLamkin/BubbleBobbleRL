"""Score a trained model the same way regardless of how it was trained.

    uv run python scripts/evaluate.py runs/<run>/model.pt

Plays every level in --levels for --episodes episodes each (1 life, sampled
actions, fixed seeds) and counts how each episode ended. This is the fitness
measure used by evolve.py: it ignores the reward the model was trained on.
"""

from __future__ import annotations

import argparse

import gymnasium as gym

import bubblebobblerl  # noqa: F401  (registers BubbleBobble-v0)

try:
    import torch
except ImportError:
    raise SystemExit("torch is required: uv sync --extra train")

from train_ppo import Agent, parse_levels


def evaluate(
    model_path: str,
    levels: list[int],
    episodes: int = 3,
    max_steps: int = 900,
    seed: int = 0,
    obs: str = "state",
) -> dict:
    env = gym.make("BubbleBobble-v0", obs_type=obs)
    agent = Agent.load(model_path, env.observation_space, env.action_space.n)
    game = env.unwrapped.game
    # Own generator, so results do not depend on the caller's torch RNG state.
    gen = torch.Generator().manual_seed(seed)

    cleared = died = timeout = 0
    score = 0
    per_level: dict[int, int] = {}
    for level in levels:
        per_level[level] = 0
        for ep in range(episodes):
            o, _ = env.reset(seed=seed * 100_003 + level * 101 + ep, options={"level": level})
            for _ in range(max_steps):
                with torch.no_grad():
                    logits = agent.actor(agent._encode(torch.as_tensor(agent.obs_in(o)[None])))
                a = torch.multinomial(torch.softmax(logits, -1), 1, generator=gen)
                o, _, term, trunc, info = env.step(int(a))
                if term or trunc:
                    break
            score += info["score"]
            if info["enemies_alive"] == 0:
                cleared += 1
                per_level[level] += 1
            elif game.game_over:
                died += 1
            else:
                timeout += 1
    n = len(levels) * episodes
    return {
        "episodes": n,
        "cleared": cleared,
        "died": died,
        "timeout": timeout,
        "levels_cleared": sum(1 for c in per_level.values() if c),
        "mean_score": score / n,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model")
    p.add_argument("--levels", default="1-100")
    p.add_argument("--episodes", type=int, default=3)
    p.add_argument("--max-steps", type=int, default=900)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--obs", choices=["state", "ego"], default="state")
    args = p.parse_args()
    r = evaluate(args.model, parse_levels(args.levels), args.episodes, args.max_steps, args.seed, args.obs)
    print(
        f"{args.model}: cleared {r['cleared']}/{r['episodes']} episodes "
        f"({r['levels_cleared']} levels), died {r['died']}, timed out {r['timeout']}, "
        f"mean score {r['mean_score']:.0f}"
    )


if __name__ == "__main__":
    main()
