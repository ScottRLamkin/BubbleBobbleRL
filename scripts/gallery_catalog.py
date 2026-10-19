"""Write exports/index.html: a catalog of every saved gameplay gallery.

    uv run python scripts/gallery_catalog.py            # rescan exports/ and rewrite the catalog

Each gallery lives in its own folder under exports/ (written by
scripts/export_levels.py) and is never modified here. A folder with an
identity.json (policy, checkpoint hash, game revision, recording settings) is
listed with those details; older folders without one are listed with the
policy named on their own page and "unknown" for anything not recorded.

To add a version: run export_levels.py with --out exports/<YYYY-MM-DD_HHMMSS>-<label>,
write identity.json next to its index.html, then rerun this script.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path

EXPORTS = Path(__file__).resolve().parents[1] / "exports"


def describe(folder: Path) -> dict:
    page = (folder / "index.html").read_text(errors="replace")
    m = re.search(r"<p>(.*?) &middot; cleared (\d+) of (\d+) levels(.*?)</p>", page, re.S)
    gifs = len(list(folder.glob("level_*.gif")))
    ident = json.loads((folder / "identity.json").read_text()) if (folder / "identity.json").exists() else None
    row = {
        "folder": folder.name,
        "when": ident["created"] if ident else dt.datetime.fromtimestamp(folder.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M") + " (folder time)",
        "policy": ident["policy"] if ident else (html.unescape(m.group(1)) if m else "unknown"),
        "game": ident["game_revision"] if ident else "unknown (recorded before galleries kept their game revision)",
        "settings": ident["recording"] if ident else "unknown",
        "result": (f"{m.group(2)} of {m.group(3)} levels cleared {html.unescape(m.group(4)).strip()}".strip()
                   if m else "?"),
        "clips": gifs,
        "sort": dt.datetime.fromtimestamp(folder.stat().st_mtime).isoformat(),
    }
    return row


def main() -> None:
    rows = sorted((describe(p.parent) for p in EXPORTS.glob("*/index.html")), key=lambda r: r["sort"], reverse=True)
    body = "\n".join(
        f"<tr><td>{html.escape(r['when'])}</td>"
        f"<td><a href=\"{html.escape(r['folder'])}/index.html\">{html.escape(r['folder'])}</a></td>"
        f"<td>{html.escape(r['policy'])}</td><td>{html.escape(r['game'])}</td>"
        f"<td>{html.escape(r['settings'])}</td><td>{html.escape(r['result'])}</td><td>{r['clips']}</td></tr>"
        for r in rows)
    (EXPORTS / "index.html").write_text(f"""<!doctype html>
<meta charset="utf-8">
<title>Gameplay galleries</title>
<style>
  body {{ background: #14161c; color: #d8e6d0; font: 14px system-ui, sans-serif; margin: 16px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid #333; padding: 6px 8px; text-align: left; vertical-align: top; }}
  a {{ color: #9fd39f; }}
  p {{ max-width: 70em; }}
</style>
<h1>Gameplay galleries</h1>
<p>Every saved version, newest first. Each folder is a separate recording and is never overwritten.
Versions differ in policy, game revision and recording settings; a visual difference between two
of them is not by itself a learning gain. Older versions picked the best of several episodes per
level; versions with an identity record show one unselected episode per level.</p>
<table>
<tr><th>recorded</th><th>version</th><th>policy</th><th>game revision</th><th>recording</th><th>result</th><th>clips</th></tr>
{body}
</table>
""")
    print(f"{EXPORTS / 'index.html'}: {len(rows)} versions")


if __name__ == "__main__":
    main()
