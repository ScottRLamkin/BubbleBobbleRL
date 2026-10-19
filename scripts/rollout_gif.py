"""Record a rollout GIF: uv run python scripts/rollout_gif.py [--policy random]

Policies: random, or "hunter" - a tiny scripted baseline that walks toward
the nearest enemy and shoots. Useful as a sanity bar for trained agents.
"""

from __future__ import annotations

import argparse

import numpy as np

from bubblebobblerl import BubbleBobbleEnv
from bubblebobblerl.render import draw_rgb


def hunter_policy(env: BubbleBobbleEnv, rng: np.random.Generator) -> int:
    g = env.game
    p = g.player
    targets = [e for e in g.enemies if not e.falling_in]
    if not targets:
        # Nothing to shoot: collect fruit, or chase captured bubbles.
        loot = g.fruits + [b for b in g.bubbles if b.captured is not None]
        if loot:
            t = min(loot, key=lambda t: abs(t.x - p.x))
            if abs(t.x - p.x) <= 2:
                return 3  # JUMP up into it
            return 1 if t.x < p.x else 2
        return 0
    e = min(targets, key=lambda e: abs(e.x - p.x) + abs(e.y - p.y))
    dx, dy = e.x - p.x, e.y - p.y
    toward = 2 if dx > 0 else 1  # 1=LEFT, 2=RIGHT
    away = 3 - toward
    same_floor = abs(dy) < 10
    if same_floor and abs(dx) < 14:
        return 6 + away  # too close: retreat while shooting
    if same_floor and abs(dx) < 34:
        return 6 + toward  # in bubble range: advance and shoot
    if dy < -6 and rng.random() < 0.15:
        return 3 + toward  # enemy above: hop toward it sometimes
    return toward


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=["random", "hunter"], default="hunter")
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=1500)
    parser.add_argument("--out", default="rollout.gif")
    args = parser.parse_args()

    try:
        import imageio.v3 as iio
    except ImportError:
        raise SystemExit("imageio is required: uv add --dev imageio")

    env = BubbleBobbleEnv(level=args.level, lives=3, frame_skip=4)
    rng = np.random.default_rng(args.seed)
    env.reset(seed=args.seed)
    frames = [draw_rgb(env.game, scale=4)]
    total = 0.0
    for _ in range(args.steps):
        if args.policy == "random":
            action = env.action_space.sample()
        else:
            action = hunter_policy(env, rng)
        _, r, term, trunc, info = env.step(action)
        total += r
        frames.append(draw_rgb(env.game, scale=4))
        if term or trunc:
            break

    iio.imwrite(args.out, frames, duration=33, loop=0)
    print(
        f"{args.policy}: {len(frames)} frames, score={info['score']}, "
        f"return={total:.2f}, enemies left={info['enemies_alive']} -> {args.out}"
    )


if __name__ == "__main__":
    main()
