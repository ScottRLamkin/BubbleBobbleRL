"""Skill diagnostic: does the agent go to a reachable, stationary target?

    uv run python scripts/diag_fixture.py runs/<run>/best.pt --obs ego --control-obs --out runs/analysis/diag-1019/fix_<name>.json
    uv run python scripts/diag_fixture.py --policy random --out ...

Fixture, not generalisation evidence: level 1's geometry, the player placed
on the bottom floor, ONE Buster placed on the same floor at a fixed offset
(+40 or -40 px, both sides, several start columns), all other enemies
removed. The target is frozen (it never activates) so it cannot come to the
player: any closing of the gap is the player's doing. Per situation we
record whether the player's x came within `--reach` px of the target within
the step cap, the time to get there, and the sign of the first horizontal
displacement. Controls: --policy random, and a stationary policy is simply
one that never arrives. Mirrored situations control for a left/right bias.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from bubblebobblerl import BubbleBobbleEnv
from bubblebobblerl.env import ACTIONS
from bubblebobblerl.game import Enemy

try:
    import torch
except ImportError:
    raise SystemExit("torch is required: uv sync --extra train")

from train_ppo import Agent

FLOOR_Y = 52  # level 1 bottom floor, the normal spawn row
START_XS = (16, 32, 48)  # player start columns; targets at +-40 px stay on the floor (8..88)


def situations():
    for sx in START_XS:
        for side in (+1, -1):
            tx = sx + 40 * side
            if 0 <= tx <= 88:
                yield {"player_x": sx, "target_x": tx, "side": side}


def run_one(env, agent, policy, gen, rng, sit, max_steps, reach):
    env.reset(seed=1, options={"level": 1})
    g = env.game
    g.player.x, g.player.y = sit["player_x"], FLOOR_Y
    g.player.facing = sit["side"]
    target = Enemy(kind=0, x=sit["target_x"], y=FLOOR_Y, facing=-sit["side"], spawn_delay=10**9,
                   falling_in=True)  # never activates: frozen, harmless, visible as "falling in"
    g.enemies = [target]
    g.alive_enemies = 1
    env._xs = []
    env._visited = {g.player.x // 8}
    o = env._obs()
    first_dir = 0
    arrived_at = None
    x0 = g.player.x
    for step in range(max_steps):
        if policy == "random":
            a = int(rng.integers(len(ACTIONS)))
        else:
            with torch.no_grad():
                logits = agent.actor(agent._encode(torch.as_tensor(agent.obs_in(o)[None])))
            a = int(torch.multinomial(torch.softmax(logits, -1), 1, generator=gen))
        o, _, term, trunc, _ = env.step(a)
        x = g.player.x
        if first_dir == 0 and x != x0:
            first_dir = int(np.sign(x - x0))
        if arrived_at is None and abs(x - sit["target_x"]) <= reach:
            arrived_at = step + 1
            break
        if term or trunc:
            break
    return {"situation": sit, "arrived_step": arrived_at,
            "first_move_toward_target": first_dir == sit["side"] if first_dir else None,
            "final_gap_px": abs(g.player.x - sit["target_x"])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", nargs="?")
    p.add_argument("--policy", choices=["model", "random"], default="model")
    p.add_argument("--obs", choices=["state", "ego"], default="state")
    p.add_argument("--control-obs", action="store_true")
    p.add_argument("--episodes", type=int, default=5, help="per situation")
    p.add_argument("--max-steps", type=int, default=150, help="10 s at 15 steps/s")
    p.add_argument("--reach", type=int, default=16)
    p.add_argument("--seed", type=int, default=7777)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    env = BubbleBobbleEnv(obs_type=args.obs, control_obs=args.control_obs,
                          max_episode_frames=4 * args.max_steps, level=1)
    agent = Agent.load(args.model, env.observation_space, env.action_space.n) if args.policy == "model" else None
    gen = torch.Generator().manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    records = []
    for sit in situations():
        for ep in range(args.episodes):
            records.append(run_one(env, agent, args.policy, gen, rng, sit, args.max_steps, args.reach))
    n = len(records)
    arrived = [r for r in records if r["arrived_step"] is not None]
    by_side = {}
    for side in (+1, -1):
        rs = [r for r in records if r["situation"]["side"] == side]
        by_side[side] = sum(r["arrived_step"] is not None for r in rs) / len(rs)
    toward = [r["first_move_toward_target"] for r in records if r["first_move_toward_target"] is not None]
    summary = {
        "situations": len(list(situations())), "episodes": n,
        "arrival_rate": len(arrived) / n,
        "arrival_rate_target_right": by_side[+1], "arrival_rate_target_left": by_side[-1],
        "median_steps_to_arrive": float(np.median([r["arrived_step"] for r in arrived])) if arrived else None,
        "first_move_toward_rate": sum(toward) / len(toward) if toward else None,
        "episodes_with_any_move": len(toward),
        "mean_final_gap_px": float(np.mean([r["final_gap_px"] for r in records])),
    }
    json.dump({"model": args.model, "policy": args.policy, "seed": args.seed, "reach": args.reach,
               "max_steps": args.max_steps, "summary": summary, "records": records},
              open(args.out, "w"), indent=1)
    print(json.dumps({"model": args.model or "random", **summary}))


if __name__ == "__main__":
    main()
