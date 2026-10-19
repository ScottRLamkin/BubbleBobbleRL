"""Record a new, versioned gameplay gallery with the existing generator.

    uv run python scripts/record_gallery.py --checkpoint runs/hparam-1019-v2/conf/ff12_s4201/model.pt \\
        --snapshot runs/hparam-1019-v2/snapshot --label hparam-1019-v2-ff12-s4201

Runs scripts/export_levels.py FROM THE GIVEN SNAPSHOT (so the game, observation
and loader are the ones the checkpoint was trained and evaluated with) into a
new folder exports/<YYYY-MM-DD_HHMMSS>-<label>-<checkpoint hash prefix>, writes
identity.json next to its index.html, and refreshes exports/index.html. Existing
folders are never touched. Recording settings are fixed here so versions are
comparable: levels 1-99, one unselected episode per level (env and torch seed 0,
the generator's own scheme), 900 decisions (the campaign's one-minute cap),
sampled actions, scale 3.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--snapshot", required=True, help="campaign snapshot folder holding src/ and scripts/")
    p.add_argument("--label", required=True)
    p.add_argument("--note", default="", help="known limitations of this policy/game pair, shown in identity.json")
    a = p.parse_args()
    ckpt = Path(a.checkpoint).resolve()
    snap = Path(a.snapshot).resolve()
    sha = hashlib.sha256(ckpt.read_bytes()).hexdigest()
    arch = json.loads((ckpt.parent / "arch.json").read_text())
    config = json.loads((ckpt.parent / "config.json").read_text())
    snap_info = json.loads((snap.parent / "snapshot.json").read_text()) if (snap.parent / "snapshot.json").exists() else {}
    for prior in (REPO / "exports").glob("*/identity.json"):  # duplicate-safe on restart
        if json.loads(prior.read_text()).get("checkpoint_sha256") == sha:
            print(f"already recorded: {prior.parent / 'index.html'}")
            return
    stamp = dt.datetime.now().astimezone()
    out = REPO / "exports" / f"{stamp:%Y-%m-%d_%H%M%S}-{a.label}-{sha[:8]}"
    if out.exists():
        raise SystemExit(f"{out} exists; versions are never overwritten")
    settings = {"levels": "1-99", "episodes": 1, "max_steps": 900, "scale": 3, "greedy": False}
    argv = [sys.executable, str(snap / "scripts" / "export_levels.py"), str(ckpt), "--obs", arch["obs"],
            "--levels", settings["levels"], "--episodes", str(settings["episodes"]),
            "--max-steps", str(settings["max_steps"]), "--scale", str(settings["scale"]), "--out", str(out)]
    argv += ["--control-obs"] if arch.get("control_obs") else []
    argv += ["--nearest-first"] if arch.get("nearest_first") else []
    env = {**os.environ, "PYTHONPATH": f"{snap / 'src'}:{snap / 'scripts'}", "OMP_NUM_THREADS": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    t0 = time.time()
    subprocess.run(argv, env=env, check=True)
    identity = {
        "created": f"{stamp:%Y-%m-%d %H:%M:%S %Z}",
        "policy": f"{a.label} ({ckpt.relative_to(REPO) if ckpt.is_relative_to(REPO) else ckpt})",
        "checkpoint": str(ckpt), "checkpoint_sha256": sha,
        "training_seed": config.get("seed"), "training_config": str(ckpt.parent / "config.json"),
        "observation": {k: arch.get(k) for k in ("obs", "control_obs", "nearest_first", "frame_skip")},
        "game_revision": f"snapshot {snap_info.get('commit', 'unknown')[:10]} ({snap_info.get('campaign', snap)})",
        "recording": "levels 1-99, 1 unselected episode each (seed 0), 900 decisions (60 s), sampled actions",
        "settings": settings, "generator": str(snap / "scripts" / "export_levels.py"),
        "seconds": round(time.time() - t0, 1),
        "note": "A viewing artifact: one episode per level, not a performance estimate." + (
            f" {a.note}" if a.note else ""),
    }
    (out / "identity.json").write_text(json.dumps(identity, indent=1))
    # The frozen generator's page says "best of several episodes each"; this
    # NEW page shows one unselected episode per level, so say that, and show
    # the identity and limitations on the page (older pages are not touched).
    page = (out / "index.html").read_text()
    page = page.replace("(best of several episodes each)", "(one unselected episode per level)")
    import html as _html

    box = (f'<p style="max-width:70em">Policy: {_html.escape(identity["policy"])} &middot; checkpoint '
           f'{sha[:12]} &middot; game: {_html.escape(identity["game_revision"])} &middot; recorded '
           f'{_html.escape(identity["created"])} &middot; {_html.escape(identity["recording"])}. '
           f'{_html.escape(identity["note"])} <a href="identity.json">identity.json</a></p>')
    page = page.replace("<main>", box + "\n<main>", 1)
    (out / "index.html").write_text(page)
    subprocess.run([sys.executable, str(REPO / "scripts" / "gallery_catalog.py")], check=True)
    print(f"version: {out / 'index.html'}\ncatalog: {REPO / 'exports' / 'index.html'}")


if __name__ == "__main__":
    main()
