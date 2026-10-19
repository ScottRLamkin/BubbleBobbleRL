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
START_XS = (40, 44, 48)  # player start columns, mid-floor so +-OFFSET stays on the floor both ways
OFFSET = 36  # px to the target; balanced: three targets left, three right


def situations(game=None):
    for sx in START_XS:
        for side in (+1, -1):
            tx = sx + OFFSET * side
            if 0 <= tx <= 88 and (game is None or (game.standing(sx, FLOOR_Y) and game.standing(tx, FLOOR_Y))):
                yield {"player_x": sx, "target_x": tx, "side": side}


# Scripted policies with known behaviour, to validate the fixture itself:
# oracle walks toward the target when there is one (and stands still when
# there is none), left/right always walk one way, noop never moves.
def _oracle(g):
    if not g.enemies:
        return 0
    dx = g.enemies[0].x - g.player.x
    return 0 if dx == 0 else (2 if dx > 0 else 1)


def _standoff(g, _state={"t": 0}):
    """Approach to 24 px, then shoot toward the target (alternating SHOOT and
    NOOP so each shot is a fresh press); stand still when there is no target."""
    _state["t"] += 1
    if not g.enemies:
        return 0
    dx = g.enemies[0].x - g.player.x
    if abs(dx) > 24:
        return 2 if dx > 0 else 1
    if g.player.facing != (1 if dx > 0 else -1):
        return 2 if dx > 0 else 1  # turn to face it (one step of movement)
    return 6 if _state["t"] % 2 else 0


SCRIPTED = {"oracle": _oracle, "standoff": _standoff, "left": lambda g: 1, "right": lambda g: 2,
            "noop": lambda g: 0}


def run_one(env, agent, policy, gen, rng, sit, max_steps, reach, facing, present, target_kind="falling",
            stop_on_arrival=True):
    """One probe. target_kind="falling": the target is held in the falling-in
    state under an unbounded grace period, so Game never moves it (grace
    blocks _step_falling_in); the observation encodes it as a falling-in enemy
    (0.5), which a policy never saw at floor level in training.
    target_kind="live": the target is an ordinary walking Buster (observation
    identical to a live enemy), frozen by disabling the enemy update for this
    game instance, so it neither moves, kills, nor gets captured. `facing` is
    set independently of the target side; `present=False` is the
    target-absent control (same player state, arrival measured at the
    would-be target x)."""
    env.reset(seed=1, options={"level": 1})
    g = env.game
    g.player.x, g.player.y = sit["player_x"], FLOOR_Y
    g.player.facing = facing
    g.grace_left = 10**9
    if present and target_kind == "falling":
        g.enemies = [Enemy(kind=0, x=sit["target_x"], y=FLOOR_Y, facing=-sit["side"], spawn_delay=10**9,
                           falling_in=True)]
    elif present:
        g.enemies = [Enemy(kind=0, x=sit["target_x"], y=FLOOR_Y, facing=-sit["side"], spawn_delay=0,
                           falling_in=False, state=1)]
    else:
        g.enemies = []
    g._step_enemies = (lambda ev: None) if target_kind == "live" else type(g)._step_enemies.__get__(g)
    g.alive_enemies = 1  # keep the level "alive" either way
    env._xs = []
    env._visited = {g.player.x // 8}
    o = env._obs()
    first_dir = 0
    arrived_at = None
    x0 = g.player.x
    ty = FLOOR_Y
    tx = sit["target_x"]
    xs = [x0]
    shots = shots_facing_target = 0
    for step in range(max_steps):
        if policy == "random":
            a = int(rng.integers(len(ACTIONS)))
        elif policy in SCRIPTED:
            a = SCRIPTED[policy](g)
        else:
            with torch.no_grad():
                logits = agent.actor(agent._encode(torch.as_tensor(agent.obs_in(o)[None])))
            a = int(torch.multinomial(torch.softmax(logits, -1), 1, generator=gen))
        n_pre = len(g.prebubbles)
        o, _, term, trunc, _ = env.step(a)
        x = g.player.x
        xs.append(x)
        if len(g.prebubbles) > n_pre:  # a new bubble was blown this step
            shots += 1
            shots_facing_target += g.player.facing == (1 if tx > x else -1)
        if present:
            assert g.enemies and g.enemies[0].x == sit["target_x"] and g.enemies[0].y == ty, "target moved"
        if first_dir == 0 and x != x0:
            first_dir = int(np.sign(x - x0))
        if arrived_at is None and abs(x - tx) <= reach and abs(g.player.y - ty) <= 8:
            arrived_at = step + 1
            if stop_on_arrival:
                break
        if term or trunc:
            break
    gaps = [abs(v - tx) for v in xs]
    at = lambda k: gaps[min(k, len(gaps) - 1)]  # noqa: E731  gap after k steps (last value if ended)
    return {"situation": sit, "facing": facing, "target_present": present, "arrived_step": arrived_at,
            "first_move_toward_target": first_dir == sit["side"] if first_dir else None,
            "final_gap_px": abs(g.player.x - tx), "min_gap_px": min(gaps),
            "gap_at_10": at(10), "gap_at_20": at(20), "gap_at_40": at(40),
            "steps": len(xs) - 1, "shots": shots, "shots_facing_target": shots_facing_target,
            "xs": xs}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", nargs="?")
    p.add_argument("--policy", choices=["model", "random", *SCRIPTED], default="model")
    p.add_argument("--obs", choices=["state", "ego"], default="state")
    p.add_argument("--control-obs", action="store_true")
    p.add_argument("--episodes", type=int, default=5, help="per situation")
    p.add_argument("--max-steps", type=int, default=150, help="10 s at 15 steps/s")
    p.add_argument("--reach", type=int, default=8, help="arrival = |x - target| within this many px")
    p.add_argument("--target", choices=["falling", "live"], default="falling")
    p.add_argument("--full-horizon", action="store_true",
                   help="do not stop at arrival (engagement measures need the whole probe)")
    p.add_argument("--seed", type=int, default=7777)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    # The env keeps the training clock (one minute) so a control-obs policy sees
    # the time-left it was trained with; the probe cap is enforced by the loop.
    env = BubbleBobbleEnv(obs_type=args.obs, control_obs=args.control_obs,
                          max_episode_frames=3600, level=1)
    agent = Agent.load(args.model, env.observation_space, env.action_space.n) if args.policy == "model" else None
    env.reset(seed=1, options={"level": 1})
    sits = list(situations(env.game))
    assert len(sits) == 6 and sum(s["side"] for s in sits) == 0, sits  # three each side, all on the floor
    records = []
    for sit in sits:
        for facing in (+1, -1):  # facing balanced against target side
            for present in (True, False):  # target-absent control with the same player state
                for ep in range(args.episodes):
                    # Matched randomness: a target-present probe and its
                    # target-absent counterpart get the same sampling stream.
                    key = (args.seed, sits.index(sit), facing, ep)
                    seed = abs(hash(key)) % (2**31)
                    gen = torch.Generator().manual_seed(seed)
                    rng = np.random.default_rng(seed)
                    records.append(run_one(env, agent, args.policy, gen, rng, sit, args.max_steps,
                                           args.reach, facing, present, args.target,
                                           not args.full_horizon))
    n = len(records)

    def block(present):
        rs = [r for r in records if r["target_present"] == present]
        arrived = [r for r in rs if r["arrived_step"] is not None]
        by_side = {s: (sum(r["arrived_step"] is not None for r in rs if r["situation"]["side"] == s)
                       / max(1, sum(1 for r in rs if r["situation"]["side"] == s))) for s in (+1, -1)}
        toward = [r["first_move_toward_target"] for r in rs if r["first_move_toward_target"] is not None]
        return {
            "episodes": len(rs), "arrival_rate": len(arrived) / len(rs),
            "arrival_rate_target_right": by_side[+1], "arrival_rate_target_left": by_side[-1],
            "median_steps_to_arrive": float(np.median([r["arrived_step"] for r in arrived])) if arrived else None,
            "first_move_toward_rate": sum(toward) / len(toward) if toward else None,
            "episodes_with_any_move": len(toward),
            "mean_final_gap_px": float(np.mean([r["final_gap_px"] for r in rs])),
        }

    summary = {"situations": len(sits), "episodes": n, "with_target": block(True), "target_absent": block(False)}
    json.dump({"model": args.model, "policy": args.policy, "seed": args.seed, "reach": args.reach,
               "target": args.target, "full_horizon": args.full_horizon,
               "max_steps": args.max_steps, "summary": summary, "records": records},
              open(args.out, "w"), indent=1)
    print(json.dumps({"model": args.model or "random", **summary}))


if __name__ == "__main__":
    main()
