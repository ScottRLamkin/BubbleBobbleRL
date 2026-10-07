"""Behaviour analysis of a trained agent: how episodes end, what it relies on.

    uv run python scripts/analyze.py runs/<run>/model.pt --out runs/analysis/<name>.json

Sections (each prints a Markdown table and lands in the JSON):
  outcomes   how episodes end, and when deaths happen; which enemy kind kills
  timeouts   what a timed-out episode looks like (enemies left, pops vs kills)
  actions    action distribution
  ablation   score with parts of the observation zeroed out
  levels     per-level clear rate against level features (enemies, kinds, walls)
  cap        clear rate as the per-episode step cap grows
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np

import bubblebobblerl  # noqa: F401
from bubblebobblerl import BubbleBobbleEnv
from bubblebobblerl.env import (
    ACTION_MEANINGS,
    ACTIONS,
    MAX_BUBBLES,
    MAX_ENEMIES,
    MAX_LOOT,
    MAX_PREBUBBLES,
)
from bubblebobblerl.game import FLOATER_KINDS
from bubblebobblerl.levels import GRID_COLS, GRID_ROWS, MONSTER_NAMES

try:
    import torch
except ImportError:
    raise SystemExit("torch is required: uv sync --extra train")

from train_ppo import Agent, parse_levels

# Offsets into the state vector (see BubbleBobbleEnv._obs).
P0 = 0
G0 = P0 + 8
E0 = G0 + GRID_ROWS * GRID_COLS
B0 = E0 + MAX_ENEMIES * 6
L0 = B0 + MAX_BUBBLES * 5
F0 = L0 + MAX_LOOT * 4
N = F0 + MAX_PREBUBBLES * 4

ABLATIONS = {
    "none": None,
    "no loot": slice(L0, F0),
    "no in-flight bubbles": slice(F0, N),
    "no bubbles": slice(B0, L0),
    "no enemies": slice(E0, B0),
    "no grid": slice(G0, E0),
}


def load_agent(model_path: str) -> Agent:
    env = BubbleBobbleEnv(obs_type="state")
    return Agent.load(model_path, env.observation_space, env.action_space.n)


def pick(agent: Agent, obs: np.ndarray, gen: torch.Generator) -> int:
    with torch.no_grad():
        logits = agent.actor(agent._encode(torch.as_tensor(agent.obs_in(obs)[None])))
    return int(torch.multinomial(torch.softmax(logits, -1), 1, generator=gen))


def mask_obs(obs: np.ndarray, ablation: str) -> np.ndarray:
    sl = ABLATIONS[ablation]
    if sl is None:
        return obs
    obs = obs.copy()
    obs[sl] = 0.0
    return obs


def run_episode(agent, env, level, seed, gen, max_steps, ablation="none", grid_wall_only=False):
    """Play one episode and return a record of what happened."""
    o, _ = env.reset(seed=seed, options={"level": level})
    g = env.game
    kinds = {id(e): e.kind for e in g.enemies}
    actions = collections.Counter()
    pops = kills = captures = 0
    first_capture = first_kill = None
    xs = []
    killer = None
    for step in range(max_steps):
        obs = mask_obs(o, ablation)
        if grid_wall_only:
            obs = obs.copy()
            obs[G0:E0] = (obs[G0:E0] > 0).astype(np.float32)
        a = pick(agent, obs, gen)
        actions[a] += 1
        before_dead = g.player.dead_ticks >= 0
        o, r, term, trunc, info = env.step(a)
        xs.append(g.player.x)
        # Events are summed inside env.step; recover them from the score and
        # counters we can see on the game object.
        kills_now = len(g.levels[g.level_num - 1].spawns) - g.alive_enemies
        if kills_now > kills:
            if first_kill is None:
                first_kill = step
            kills = kills_now
        caps_now = sum(1 for b in g.bubbles if b.captured is not None)
        if caps_now > captures:
            if first_capture is None:
                first_capture = step
        captures = max(captures, caps_now)
        if g.player.dead_ticks >= 0 and not before_dead:
            # Nearest active enemy at the moment of death is the killer.
            p = g.player
            active = [e for e in g.enemies if not e.falling_in]
            if active:
                e = min(active, key=lambda e: abs(e.x - p.x) + abs(e.y - p.y))
                killer = {"kind": MONSTER_NAMES[e.kind], "angry": e.angry}
        if term or trunc:
            break
    outcome = "cleared" if info["enemies_alive"] == 0 else ("died" if g.game_over else "timeout")
    return {
        "level": level,
        "outcome": outcome,
        "steps": step + 1,
        "score": info["score"],
        "enemies_left": info["enemies_alive"],
        "enemies_total": len(g.level.spawns),
        "kills": kills,
        "first_kill": first_kill,
        "first_capture": first_capture,
        "killer": killer,
        "actions": dict(actions),
        "x_std": float(np.std(xs)) if xs else 0.0,
    }


def level_features(env: BubbleBobbleEnv) -> dict[int, dict]:
    feats = {}
    for lv in env._levels:
        kinds = [s.kind for s in lv.spawns]
        feats[lv.number] = {
            "enemies": len(kinds),
            "floaters": sum(k in FLOATER_KINDS for k in kinds),
            "kinds": sorted({MONSTER_NAMES[k] for k in kinds}),
            "wall_frac": float(lv.solid[1:-1, 1:-1].mean()),
            "pop_time": lv.pop_time or 256,
        }
    return feats


def md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model")
    p.add_argument("--baseline", default=None, help="second model for the per-level comparison")
    p.add_argument("--levels", default="1-100")
    p.add_argument("--episodes", type=int, default=5)
    p.add_argument("--max-steps", type=int, default=900)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default=None)
    p.add_argument("--sections", default="outcomes,timeouts,actions,ablation,levels,cap")
    args = p.parse_args()
    sections = set(args.sections.split(","))

    levels = parse_levels(args.levels)
    env = BubbleBobbleEnv(obs_type="state")
    agent = load_agent(args.model)
    report: dict = {"model": args.model}

    def episodes(agent, ablation="none", grid_wall_only=False, max_steps=None, eps=None):
        gen = torch.Generator().manual_seed(args.seed)
        recs = []
        for level in levels:
            for ep in range(eps or args.episodes):
                recs.append(run_episode(
                    agent, env, level, args.seed * 100_003 + level * 101 + ep, gen,
                    max_steps or args.max_steps, ablation, grid_wall_only,
                ))
        return recs

    base = episodes(agent)
    report["episodes"] = base

    if "outcomes" in sections:
        n = len(base)
        counts = collections.Counter(r["outcome"] for r in base)
        deaths = [r for r in base if r["outcome"] == "died"]
        death_steps = np.array([r["steps"] for r in deaths])
        bins = [(0, 75, "< 5 s"), (75, 225, "5-15 s"), (225, 450, "15-30 s"), (450, 10**9, "> 30 s")]
        timing = [(label, int(((death_steps >= lo) & (death_steps < hi)).sum())) for lo, hi, label in bins]
        killers = collections.Counter(r["killer"]["kind"] for r in deaths if r["killer"])
        angry = sum(1 for r in deaths if r["killer"] and r["killer"]["angry"])
        no_kill = sum(1 for r in deaths if r["kills"] == 0)
        report["outcomes"] = {
            "counts": dict(counts), "death_timing": timing, "killers": dict(killers),
            "angry_killers": angry, "deaths_before_first_kill": no_kill,
        }
        print("\n### Outcomes\n")
        print(md_table(["Outcome", "Episodes", "Share"],
                       [(k, v, f"{100 * v / n:.0f}%") for k, v in counts.most_common()]))
        print("\n### When deaths happen\n")
        print(md_table(["Time of death", "Deaths"], timing))
        print(f"\nDeaths before the agent's first kill: {no_kill} of {len(deaths)}. "
              f"Killer was angry (the last enemy, or an escaped one): {angry} of {len(deaths)}.")
        print("\n### Which enemy kind kills\n")
        kinds_total = collections.Counter()
        for lv in env._levels:
            if lv.number in levels:
                for s in lv.spawns:
                    kinds_total[MONSTER_NAMES[s.kind]] += args.episodes
        print(md_table(["Kind", "Kills of the player", "Per 100 of that kind in play"],
                       [(k, v, f"{100 * v / kinds_total[k]:.1f}") for k, v in killers.most_common()]))

    if "timeouts" in sections:
        tos = [r for r in base if r["outcome"] == "timeout"]
        if tos:
            left = collections.Counter(r["enemies_left"] for r in tos)
            no_kill = sum(1 for r in tos if r["kills"] == 0)
            one_left = sum(1 for r in tos if r["enemies_left"] == 1)
            still = sum(1 for r in tos if r["x_std"] < 4)
            report["timeouts"] = {"n": len(tos), "enemies_left": dict(left), "no_kill": no_kill,
                                  "one_left": one_left, "standing_still": still}
            print("\n### Timed-out episodes\n")
            print(md_table(["Enemies left at timeout", "Episodes"], sorted(left.items())))
            print(f"\nOf {len(tos)} timeouts: {no_kill} with no kill at all, {one_left} with a single "
                  f"enemy left, {still} where the player barely moved (x std < 4 px).")

    if "actions" in sections:
        total = collections.Counter()
        for r in base:
            total.update({int(k): v for k, v in r["actions"].items()})
        n = sum(total.values())
        report["actions"] = {ACTION_MEANINGS[k]: v for k, v in total.items()}
        print("\n### Action distribution\n")
        print(md_table(["Action", "Share"],
                       [(ACTION_MEANINGS[k], f"{100 * v / n:.1f}%") for k, v in total.most_common()]))

    if "ablation" in sections:
        rows = []
        for name in ABLATIONS:
            recs = base if name == "none" else episodes(agent, ablation=name)
            c = collections.Counter(r["outcome"] for r in recs)
            rows.append((name, c["cleared"], c["died"], c["timeout"]))
        recs = episodes(agent, grid_wall_only=True)
        c = collections.Counter(r["outcome"] for r in recs)
        rows.append(("grid as wall/air only (no currents)", c["cleared"], c["died"], c["timeout"]))
        report["ablation"] = rows
        print("\n### Observation ablation (zeroing inputs at play time)\n")
        print(md_table(["Inputs removed", "Cleared", "Died", "Timed out"], rows))

    if "levels" in sections:
        feats = level_features(env)
        per = collections.defaultdict(lambda: collections.Counter())
        for r in base:
            per[r["level"]][r["outcome"]] += 1
        base_per = None
        if args.baseline:
            bagent = load_agent(args.baseline)
            base_per = collections.defaultdict(lambda: collections.Counter())
            for r in episodes(bagent):
                base_per[r["level"]][r["outcome"]] += 1
        rows = []
        for lv in levels:
            f = feats[lv]
            row = {"level": lv, **f, "cleared": per[lv]["cleared"], "died": per[lv]["died"],
                   "timeout": per[lv]["timeout"]}
            if base_per is not None:
                row["baseline_cleared"] = base_per[lv]["cleared"]
            rows.append(row)
        report["levels"] = rows
        E = args.episodes

        def rate(sel):
            sel = list(sel)
            return f"{100 * sum(r['cleared'] for r in sel) / (E * len(sel)):.0f}% ({len(sel)} levels)" if sel else "-"

        print("\n### Clear rate by level features\n")
        print(md_table(["Feature", "Clear rate"], [
            ("2-3 enemies", rate(r for r in rows if r["enemies"] <= 3)),
            ("4-5 enemies", rate(r for r in rows if 4 <= r["enemies"] <= 5)),
            ("6+ enemies", rate(r for r in rows if r["enemies"] >= 6)),
            ("no floaters", rate(r for r in rows if r["floaters"] == 0)),
            ("some floaters", rate(r for r in rows if 0 < r["floaters"] < r["enemies"])),
            ("all floaters", rate(r for r in rows if r["floaters"] == r["enemies"])),
            ("sparse walls (< 20%)", rate(r for r in rows if r["wall_frac"] < 0.2)),
            ("medium walls (20-35%)", rate(r for r in rows if 0.2 <= r["wall_frac"] < 0.35)),
            ("dense walls (35%+)", rate(r for r in rows if r["wall_frac"] >= 0.35)),
        ]))
        for kind in MONSTER_NAMES:
            sel = [r for r in rows if kind in r["kinds"]]
            print(f"- levels with a {kind}: {rate(sel)}")
        never = [r["level"] for r in rows if r["cleared"] == 0]
        always = [r["level"] for r in rows if r["cleared"] == E]
        print(f"\nNever cleared ({len(never)}): {never}\nAlways cleared ({len(always)}): {always}")
        if base_per is not None:
            better = [r["level"] for r in rows if r["cleared"] > r["baseline_cleared"] + 1]
            worse = [r["level"] for r in rows if r["cleared"] + 1 < r["baseline_cleared"]]
            print(f"Clearly better than baseline on {len(better)} levels: {better}")
            print(f"Clearly worse than baseline on {len(worse)} levels: {worse}")

    if "cap" in sections:
        rows = []
        for cap in (450, 900, 1800, 3600):
            recs = base if cap == args.max_steps else episodes(agent, max_steps=cap, eps=2)
            c = collections.Counter(r["outcome"] for r in recs)
            n = len(recs)
            rows.append((f"{cap} steps ({cap * 4 / 60:.0f} s)", f"{100 * c['cleared'] / n:.1f}%",
                         f"{100 * c['died'] / n:.1f}%", f"{100 * c['timeout'] / n:.1f}%"))
        report["cap"] = rows
        print("\n### Effect of the episode time limit\n")
        print(md_table(["Cap", "Cleared", "Died", "Timed out"], rows))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=1, default=str))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
