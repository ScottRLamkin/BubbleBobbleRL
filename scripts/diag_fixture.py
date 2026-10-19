"""Engagement probe: how does a policy act toward one reachable, frozen enemy?

    uv run python scripts/diag_fixture.py runs/<run>/best.pt --obs ego --control-obs \
        --target live --full-horizon --out runs/analysis/diag-1019/fix_<name>.json
    uv run python scripts/diag_fixture.py --policy standoff --target live --full-horizon --out ...
    uv run python scripts/diag_fixture.py --report a.json b.json      # matched-pair table

Fixture, not generalisation evidence: level 1's geometry, the player placed on
the bottom floor, ONE Buster on the same floor 36 px left or right (three start
columns, both sides, both initial facings), all other enemies removed, against
the same situation with the spot empty (matched sampling stream). The target
is frozen so any closing of the gap is the player's doing.

Per probe: the horizontal trace (xs) and vertical trace (ys); horizontal gap
measures (min, at 10/20/40 steps) and the minimum horizontal gap while in the
target's vertical band (|dy| <= 7, the game's capture margin); and every
bubble the player blew, recorded where Game._blow_bubbles creates it, with its
launch position and facing. A shot is "facing the target" when its launch
facing points at the target's side, and "would capture" when its flight path
(1 px/frame for the prebubble's lifetime, stopping at walls) passes within the
capture margin of the target in both axes. The frozen target is never actually
captured (its update is disabled), so "would capture" is geometric.

Superseded measure (kept as shots_net_proxy for comparison with files written
before 2026-10-19 09:40): net growth of the prebubble list across an agent
step, attributed with the post-step facing. It misses a shot blown in the step
in which an older bubble expires, and it credits a turn-and-shoot action to
the new facing although the bubble is blown before the turn.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from bubblebobblerl import BubbleBobbleEnv
from bubblebobblerl.env import ACTIONS
from bubblebobblerl.game import PREBUBBLE_FRAMES, Enemy

try:
    import torch
except ImportError:
    raise SystemExit("torch is required: uv sync --extra train")

from train_ppo import Agent

FLOOR_Y = 52  # level 1 bottom floor, the normal spawn row
START_XS = (40, 44, 48)  # player start columns, mid-floor so +-OFFSET stays on the floor both ways
OFFSET = 36  # px to the target; balanced: three targets left, three right
CAPTURE_MARGIN = 7  # Game._enemy_hazards: prebubble within 7 px of the enemy in x and y
CONTACT_MARGIN = 5  # Game._touch_player: a live enemy this close kills the player


def derived_measures(r) -> dict:
    """Measures that separate shooting from a distance from shooting while
    standing on the target. The frozen target is harmless, so a policy can
    stand inside it, where the real game would have killed it, and any bubble
    blown there captures regardless of facing. steps_in_contact counts steps
    within the contact margin of the target spot in both axes;
    shots_ranged_capture counts would-capture shots launched more than the
    capture margin away (the bubble had to travel to the target)."""
    tx, ty = r["situation"]["target_x"], FLOOR_Y
    return {
        "steps_in_contact": sum(abs(x - tx) <= CONTACT_MARGIN and abs(y - ty) <= CONTACT_MARGIN
                                for x, y in zip(r["xs"][1:], r["ys"][1:])),
        "shots_ranged_capture": sum(e["would_capture"] and abs(e["x"] - tx) > CAPTURE_MARGIN
                                    for e in r["shot_events"]),
    }


def instrument_shots(g) -> list[dict]:
    """Record every bubble blown in this game instance at its creation:
    {"frame", "x", "y", "facing"} (launch position and facing)."""
    events: list[dict] = []
    # Bind the class method, not g._blow_bubbles: the env reuses its Game across
    # resets, so wrapping the instance attribute would stack one wrapper per
    # probe and keep appending to earlier probes' lists.
    orig = type(g)._blow_bubbles.__get__(g)

    def blow(p, shoot_held, shoot_pressed):
        n = len(g.prebubbles)
        orig(p, shoot_held, shoot_pressed)
        if len(g.prebubbles) > n:  # nothing else touches the list inside this call
            pb = g.prebubbles[-1]
            events.append({"frame": g.timer, "x": pb.x, "y": pb.y, "facing": pb.facing})

    g._blow_bubbles = blow
    return events


def would_capture(g, x, y, facing, tx, ty) -> bool:
    """Does a prebubble launched at (x, y) facing `facing` pass within the
    capture margin of (tx, ty)? Mirrors Game._step_prebubbles (moves 1 px per
    frame unless the wall probe is solid) and the capture test, which runs
    after the move on every frame the bubble is still a prebubble."""
    if abs(g._delta_wrapped(y, ty)) > CAPTURE_MARGIN:
        return False
    for _ in range(PREBUBBLE_FRAMES - 1):  # removed before the hazard test on its last frame
        probe_x = x + 8 if facing > 0 else x - 1
        if not g.solid(probe_x, y + 7):
            x += facing
        if abs(x - tx) <= CAPTURE_MARGIN:
            return True
    return False


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
    shot_events = instrument_shots(g)
    g.alive_enemies = 1  # keep the level "alive" either way
    env._xs = []
    env._visited = {g.player.x // env.explore_band}
    o = env._obs()
    first_dir = 0
    arrived_at = None
    x0 = g.player.x
    ty = FLOOR_Y
    tx = sit["target_x"]
    xs = [x0]
    ys = [g.player.y]
    proxy_shots = proxy_facing = 0
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
        ys.append(g.player.y)
        if len(g.prebubbles) > n_pre:  # superseded proxy, see the module docstring
            proxy_shots += 1
            proxy_facing += g.player.facing == (1 if tx > x else -1)
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
    gaps = [abs(v - tx) for v in xs]  # horizontal only
    aligned = [abs(v - tx) for v, y in zip(xs, ys) if abs(g._delta_wrapped(y, ty)) <= CAPTURE_MARGIN]
    at = lambda k: gaps[min(k, len(gaps) - 1)]  # noqa: E731  gap after k steps (last value if ended)
    for e in shot_events:
        e["facing_target"] = e["facing"] == (1 if tx > e["x"] else -1 if tx < e["x"] else 0)
        e["would_capture"] = would_capture(g, e["x"], e["y"], e["facing"], tx, ty)
    rec = {"situation": sit, "facing": facing, "target_present": present, "arrived_step": arrived_at,
            "first_move_toward_target": first_dir == sit["side"] if first_dir else None,
            "final_gap_px": abs(g.player.x - tx), "min_gap_px": min(gaps),
            "min_gap_in_band_px": min(aligned) if aligned else None,
            "gap_at_10": at(10), "gap_at_20": at(20), "gap_at_40": at(40),
            "steps": len(xs) - 1, "shots": len(shot_events),
            "shots_facing_target": sum(e["facing_target"] for e in shot_events),
            "shots_would_capture": sum(e["would_capture"] for e in shot_events),
            "shot_events": shot_events,
            "shots_net_proxy": proxy_shots, "shots_net_proxy_facing_target": proxy_facing,
            "xs": xs, "ys": ys}
    rec.update(derived_measures(rec))
    return rec


REPORT_FIELDS = ("min_gap_px", "min_gap_in_band_px", "steps_in_contact", "shots", "shots_facing_target",
                 "shots_would_capture", "shots_ranged_capture")


def _sign_p(plus, minus):
    """Two-sided sign test, ties dropped."""
    from math import comb

    n = plus + minus
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, k) for k in range(min(plus, minus) + 1)) / 2**n)


def report(paths, fields=REPORT_FIELDS):
    """Per side, target present vs absent means, and matched-pair counts
    (same start column, side, facing, episode and sampling seed) of
    present > absent / present < absent with a sign test. Probes with no
    in-band step have min_gap_in_band_px None; their pairs are left out and
    counted."""
    out = []
    for path in paths:
        d = json.load(open(path))
        recs = d["records"]
        if "shot_events" not in recs[0]:
            out.append(f"{path}: written before creation-time shot recording; skipped")
            continue
        for r in recs:
            r.update(derived_measures(r))
        name = (d["model"] or d["policy"]).replace("runs/", "")
        out.append(f"{name}  (policy {d['policy']}, seed {d['seed']}, target {d['target']}, "
                   f"full_horizon {d.get('full_horizon')}, {len(recs)} probes)")
        groups: dict = {}
        for r in recs:
            k = (r["situation"]["player_x"], r["situation"]["side"], r["facing"], r["target_present"])
            groups.setdefault(k, []).append(r)
        for side, label in ((+1, "target right"), (-1, "target left")):
            out.append(f"  {label}:")
            for f in fields:
                pres = [r[f] for k, g in groups.items() if k[1] == side and k[3] for r in g]
                absn = [r[f] for k, g in groups.items() if k[1] == side and not k[3] for r in g]
                plus = minus = dropped = 0
                for k, g in groups.items():
                    if k[1] != side or not k[3]:
                        continue
                    for a, b in zip(g, groups[(k[0], k[1], k[2], False)]):
                        if a[f] is None or b[f] is None:
                            dropped += 1
                        elif a[f] > b[f]:
                            plus += 1
                        elif a[f] < b[f]:
                            minus += 1
                mean = lambda v: f"{np.mean([x for x in v if x is not None]):6.1f}" if any(  # noqa: E731
                    x is not None for x in v) else "   n/a"
                extra = f", {dropped} pairs without an in-band step" if dropped else ""
                out.append(f"    {f:22s} present {mean(pres)} absent {mean(absn)} | pairs present>absent "
                           f"{plus:2d}, < {minus:2d} (sign p={_sign_p(plus, minus):.1e}){extra}")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", nargs="?")
    p.add_argument("--report", nargs="+", metavar="JSON", help="print the matched-pair table for result files")
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
    p.add_argument("--out")
    args = p.parse_args()
    if args.report:
        print(report(args.report))
        return
    if not args.out:
        p.error("--out is required")
    # The env keeps the training clock (one minute) so a control-obs policy sees
    # the time-left it was trained with; the probe cap is enforced by the loop.
    env = BubbleBobbleEnv(obs_type=args.obs, control_obs=args.control_obs,
                          max_episode_frames=3600, level=1)
    agent = Agent.load(args.model, env.observation_space, env.action_space.n, env=env) if args.policy == "model" else None
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
            "mean_shots": float(np.mean([r["shots"] for r in rs])),
            "mean_shots_facing_target": float(np.mean([r["shots_facing_target"] for r in rs])),
            "mean_shots_would_capture": float(np.mean([r["shots_would_capture"] for r in rs])),
        }

    summary = {"situations": len(sits), "episodes": n, "with_target": block(True), "target_absent": block(False)}
    json.dump({"model": args.model, "policy": args.policy, "seed": args.seed, "reach": args.reach,
               "target": args.target, "full_horizon": args.full_horizon,
               "max_steps": args.max_steps, "summary": summary, "records": records},
              open(args.out, "w"), indent=1)
    print(json.dumps({"model": args.model or "random", **summary}))


if __name__ == "__main__":
    main()
