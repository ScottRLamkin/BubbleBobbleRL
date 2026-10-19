"""Is the agent's movement directed at anything? Trajectory-level diagnostic.

    uv run python scripts/diag_navigation.py runs/<run>/best.pt --obs ego --control-obs --out runs/analysis/diag-1019/nav_<name>.json

Plays every level once (one life, 900-step cap, sampled actions, fixed seeds)
and records per step the player's position, the offset to the nearest live
enemy, and kill/fruit events. Reports:

  approach rate   share of horizontal moves that reduce |dx| to the nearest
                  live enemy, counted only when |dx| > 24 px (a random mover
                  scores about 50%; retreating scores below)
  kills away      share of kills made with the player more than 24 px from
                  the spawn column (x > 32)
plus the usual movement figures, so navigation can be separated from motion.
Use --policy random for the random-mover control.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from bubblebobblerl import BubbleBobbleEnv
from bubblebobblerl.env import ACTIONS

try:
    import torch
except ImportError:
    raise SystemExit("torch is required: uv sync --extra train")

from train_ppo import Agent, parse_levels

SPAWN_X = 8


def nearest_enemy(game):
    p = game.player
    live = [e for e in game.enemies if not e.falling_in]
    if not live:
        return None
    e = min(live, key=lambda e: abs(e.x - p.x) + abs(game._delta_wrapped(e.y, p.y)))
    return e.x - p.x, game._delta_wrapped(e.y, p.y)


def run(model, levels, obs, control_obs, policy, seed, max_steps):
    env = BubbleBobbleEnv(obs_type=obs, control_obs=control_obs, max_episode_frames=4 * max_steps)
    agent = Agent.load(model, env.observation_space, env.action_space.n, env=env) if policy == "model" else None
    gen = torch.Generator().manual_seed(seed)
    rng = np.random.default_rng(seed)
    episodes = []
    for level in levels:
        o, _ = env.reset(seed=seed * 100_003 + level * 101, options={"level": level})
        g = env.game
        rec = {"level": level, "steps": 0, "approach": 0, "retreat": 0, "far_steps": 0,
               "kills": [], "xs": [], "outcome": None}
        prev_kills = 0
        completed = False
        for _ in range(max_steps):
            if policy == "random":
                a = int(rng.integers(len(ACTIONS)))
            else:
                with torch.no_grad():
                    logits = agent.actor(agent._encode(torch.as_tensor(agent.obs_in(o)[None])))
                a = int(torch.multinomial(torch.softmax(logits, -1), 1, generator=gen))
            before = nearest_enemy(g)
            x0 = g.player.x
            o, _, term, trunc, info = env.step(a)
            x1 = g.player.x
            rec["steps"] += 1
            rec["xs"].append(x1)
            if before is not None and abs(before[0]) > 24 and x1 != x0:
                rec["far_steps"] += 1
                if (x1 - x0) * np.sign(before[0]) > 0:
                    rec["approach"] += 1
                else:
                    rec["retreat"] += 1
            completed = completed or bool(info.get("level_complete", False))
            k = info.get("kills", 0)
            if k > prev_kills:
                rec["kills"] += [x1] * (k - prev_kills)
                prev_kills = k
            if term or trunc:
                break
        rec["outcome"] = "clear" if completed else ("death" if g.game_over else "timeout")
        rec["all_enemies_dead"] = info["enemies_alive"] == 0
        rec["x_range"] = int(max(rec["xs"]) - min(rec["xs"])) if rec["xs"] else 0
        rec["still_share"] = float(np.mean([
            max(rec["xs"][i - 30:i + 1]) - min(rec["xs"][i - 30:i + 1]) < 8 for i in range(30, len(rec["xs"]))
        ])) if len(rec["xs"]) > 30 else 1.0
        del rec["xs"]
        episodes.append(rec)
    return episodes


def summarize(episodes):
    app = sum(e["approach"] for e in episodes)
    far = sum(e["far_steps"] for e in episodes)
    kills = [x for e in episodes for x in e["kills"]]
    away = sum(1 for x in kills if x > SPAWN_X + 24)
    return {
        "episodes": len(episodes),
        "approach_rate": app / far if far else float("nan"),
        "far_move_steps": far,
        "kills_total": len(kills),
        "kills_per_episode": len(kills) / len(episodes),
        "kills_away_from_spawn_share": away / len(kills) if kills else float("nan"),
        "mean_x_range": float(np.mean([e["x_range"] for e in episodes])),
        "still_share": float(np.mean([e["still_share"] for e in episodes])),
        "clears": sum(e["outcome"] == "clear" for e in episodes),
        "deaths": sum(e["outcome"] == "death" for e in episodes),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", nargs="?", default=None)
    p.add_argument("--policy", choices=["model", "random"], default="model")
    p.add_argument("--levels", default="1-99")
    p.add_argument("--obs", choices=["state", "ego"], default="state")
    p.add_argument("--control-obs", action="store_true")
    p.add_argument("--seed", type=int, default=5150)
    p.add_argument("--max-steps", type=int, default=900)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    episodes = run(args.model, parse_levels(args.levels), args.obs, args.control_obs, args.policy,
                   args.seed, args.max_steps)
    summary = summarize(episodes)
    json.dump({"model": args.model, "policy": args.policy, "seed": args.seed, "levels": args.levels,
               "summary": summary, "episodes": episodes}, open(args.out, "w"), indent=1)
    print(json.dumps({"model": args.model or "random", **summary}))


if __name__ == "__main__":
    main()
