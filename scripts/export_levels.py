"""Export a GIF of a trained agent on every level, plus an index.html gallery.

    uv run python scripts/export_levels.py runs/<run>/model.pt
    uv run python scripts/export_levels.py runs/<run>/model.pt --levels 1-10

For each level the agent plays --episodes episodes and the best one (cleared
first, then highest return) is written to <out>/level_NNN.gif. Open
<out>/index.html to watch them all on one page.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import gymnasium as gym
import numpy as np

import bubblebobblerl  # noqa: F401  (registers BubbleBobble-v0)
from bubblebobblerl.render import draw_rgb

try:
    import imageio.v3 as iio
    import torch
except ImportError:
    raise SystemExit("torch and imageio are required: uv sync --extra train")

from train_ppo import Agent, parse_levels


def play_episode(env, agent, level: int, seed: int, max_steps: int, scale: int, greedy: bool):
    torch.manual_seed(seed)
    o, _ = env.reset(seed=seed, options={"level": level})
    game = env.unwrapped.game
    frames, total = [draw_rgb(game, scale=scale)], 0.0
    for _ in range(max_steps):
        with torch.no_grad():
            a, *_ = agent.action_value(torch.as_tensor(agent.obs_in(o)[None]), greedy=greedy)
        o, r, term, trunc, info = env.step(int(a))
        total += r
        frames.append(draw_rgb(game, scale=scale))
        if term or trunc:
            break
    cleared = info["enemies_alive"] == 0
    if cleared:
        outcome = "cleared"
    elif game.game_over:
        outcome = "died"
    else:
        outcome = "timeout"
    return {"frames": frames, "return": total, "score": info["score"],
            "cleared": cleared, "outcome": outcome}


def write_index(out: Path, rows: list[dict], model: str) -> None:
    cleared = sum(r["cleared"] for r in rows)
    cards = "\n".join(
        f'<figure class="{r["outcome"]}"><img loading="lazy" src="level_{r["level"]:03d}.gif">'
        f'<figcaption>Level {r["level"]} &middot; {r["outcome"]} &middot; '
        f'score {r["score"]}</figcaption></figure>'
        for r in rows
    )
    out.joinpath("index.html").write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<title>Bubble Bobble agent - all levels</title>
<style>
  body {{ background: #14161c; color: #d8e6d0; font: 14px system-ui, sans-serif; margin: 16px; }}
  main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(288px, 1fr)); gap: 12px; }}
  figure {{ margin: 0; border-left: 4px solid #666; padding-left: 6px; }}
  figure.cleared {{ border-color: #7ccf7c; }}
  figure.died {{ border-color: #d06060; }}
  img {{ width: 100%; image-rendering: pixelated; display: block; }}
</style>
<h1>Bubble Bobble agent</h1>
<p>{model} &middot; cleared {cleared} of {len(rows)} levels (best of several episodes each)</p>
<main>
{cards}
</main>
"""
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", help="path to a model.pt from train_ppo.py")
    p.add_argument("--obs", choices=["state", "screen", "ego"], default="state")
    p.add_argument("--levels", default="1-100", help='e.g. "1-100" or "1,5,20-30"')
    p.add_argument("--episodes", type=int, default=3)
    p.add_argument("--max-steps", type=int, default=600, help="agent steps per episode")
    p.add_argument("--scale", type=int, default=3)
    p.add_argument("--greedy", action="store_true", help="most likely action, no sampling")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    out = Path(args.out or Path("exports") / Path(args.model).parent.name)
    out.mkdir(parents=True, exist_ok=True)

    env = gym.make("BubbleBobble-v0", obs_type=args.obs)
    agent = Agent.load(args.model, env.observation_space, env.action_space.n)

    rows = []
    for level in parse_levels(args.levels):
        episodes = [
            play_episode(env, agent, level, seed, args.max_steps, args.scale, args.greedy)
            for seed in range(args.episodes)
        ]
        best = max(episodes, key=lambda e: (e["cleared"], e["return"]))
        # 4 game frames per agent step at 60 Hz -> 67 ms plays at real time.
        iio.imwrite(out / f"level_{level:03d}.gif", best["frames"], duration=67, loop=0)
        rows.append({
            "level": level,
            "outcome": best["outcome"],
            "cleared": best["cleared"],
            "score": best["score"],
            "clears": sum(e["cleared"] for e in episodes),
        })
        print(
            f"level {level:3d}: {best['outcome']:8s} score {best['score']:6d} "
            f"return {best['return']:6.2f}  ({rows[-1]['clears']}/{args.episodes} cleared)"
        )

    write_index(out, rows, args.model)
    print(
        f"cleared {sum(r['cleared'] for r in rows)}/{len(rows)} levels "
        f"-> {np.round(sum(f.stat().st_size for f in out.glob('*.gif')) / 1e6, 1)} MB in {out}/"
    )
    print(f"open {out / 'index.html'}")


if __name__ == "__main__":
    main()
