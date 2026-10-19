"""Side-by-side tables for two hparam campaigns with the same design (read-only).

    uv run python scripts/compare_campaigns.py runs/hparam-1019 runs/hparam-1019-v2

Prints Markdown: final-bank paired results, the final-bank outcome profile,
confirmation means, and the screen ranking, for each campaign. The campaigns
may differ in game version, so a cross-campaign difference is a description,
not a matched comparison of recipes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(root: Path) -> dict:
    st = json.loads((root / "status.json").read_text())
    return {"root": root, "st": st, "jobs": st["jobs"]}


def final_profile(c: dict) -> dict:
    out: dict = {}
    for j in c["jobs"].values():
        if j["phase"] != "final" or j["state"] != "done":
            continue
        f = json.loads((Path(j["dir"]) / f"eval_{j['eval_seed']}.json").read_text())
        r = out.setdefault((j["config"], j["seed"]), {"cleared": [], "died": [], "timeout": [], "kills": [], "levels": []})
        r["cleared"].append(f["cleared"])
        r["died"].append(f["died"])
        r["timeout"].append(f["timeout"])
        r["kills"].append(f["kills_per_episode"])
        r["levels"].append(f["levels_cleared"])
    return out


def mean(v):
    return sum(v) / len(v)


def main():
    roots = [Path(a) for a in sys.argv[1:]]
    cs = [load(r) for r in roots]
    names = [c["st"]["campaign"] for c in cs]
    out = ["## Final bank: paired completions per 990 (mean of the two final seeds)", ""]
    for name, c in zip(names, cs):
        fin = c["st"].get("final")
        w = (c["st"].get("frozen") or {}).get("winner")
        if not fin:
            out.append(f"{name}: no final bank")
            continue
        out += [f"**{name}** (winner {w}; accepted: {fin['accepted']}; mean gain {fin['mean_gain']:+.1f})", "",
                f"| training seed | {w} | anchor_G | gain |", "|---|---|---|---|"]
        for s, p in fin["pairs"].items():
            out.append(f"| {s} | {p['winner']} | {p['anchor_G']} | {p['gain']:+.1f} |")
        out.append("")
    out += ["## Final-bank outcome profile (per 990, ranges over the three training seeds)", "",
            "| campaign | recipe | clears | deaths | timeouts | kills per episode | levels cleared at least once |",
            "|---|---|---|---|---|---|---|"]
    for name, c in zip(names, cs):
        prof = final_profile(c)
        for recipe in sorted({k[0] for k in prof}):
            rows = [v for k, v in prof.items() if k[0] == recipe]
            rng = lambda key, fmt="{:.0f}": "{}-{}".format(  # noqa: E731
                fmt.format(min(mean(r[key]) for r in rows)), fmt.format(max(mean(r[key]) for r in rows)))
            out.append(f"| {name} | {recipe} | {rng('cleared')} | {rng('died')} | {rng('timeout')} | "
                       f"{rng('kills', '{:.2f}')} | {rng('levels')} |")
    out += ["", "## Confirmation (tuning seeds; mean of 3 training seeds x 2 evaluation seeds)", "",
            "| campaign | " + " | ".join(["recipe", "mean clears"]) + " |", "|---|---|---|"]
    for name, c in zip(names, cs):
        by: dict = {}
        for j in c["jobs"].values():
            if j["phase"] == "confirmation" and j["state"] == "done":
                by.setdefault(j["config"], []).append(mean([v["cleared"] for v in j["results"].values()]))
        for recipe, v in sorted(by.items(), key=lambda kv: -mean(kv[1])):
            out.append(f"| {name} | {recipe} | {mean(v):.1f} |")
    out += ["", "## Screen ranking (mean tuning-seed clears)", "", "| rank | " + " | ".join(names) + " |",
            "|---|" + "---|" * len(names)]
    ranks = [[(r["config"], r["mean_cleared"]) for r in (c["st"].get("selection") or {}).get("ranked", [])] for c in cs]
    for i in range(max(len(r) for r in ranks)):
        cells = [f"{r[i][0]} ({r[i][1]:.1f})" if i < len(r) else "" for r in ranks]
        out.append(f"| {i + 1} | " + " | ".join(cells) + " |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
