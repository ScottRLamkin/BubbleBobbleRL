"""Build docs/report.html from the Markdown write-ups, Mermaid diagrams included.

    uv run python scripts/build_report.py && open docs/report.html

A deliberately small Markdown subset: headings, paragraphs, bullet and
numbered lists, pipe tables, fenced code (```mermaid becomes a diagram),
inline `code`, **bold**, *italic* and links. Enough for the docs here.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
SOURCES = [
    ("analysis.md", "Behaviour analysis"),
    ("training-setup.md", "Training setup and results"),
    ("model-architecture.md", "Model architecture"),
    ("experiments.md", "Running your own experiments"),
]


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*]+)\*(?!\w)", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def convert(md: str, prefix: str) -> tuple[str, list[tuple[int, str, str]]]:
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    lines = md.splitlines()
    i = 0
    para: list[str] = []

    def flush_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_para()
            lang = line[3:].strip()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            body = "\n".join(block)
            if lang == "mermaid":
                out.append(f'<pre class="mermaid">{html.escape(body, quote=False)}</pre>')
            else:
                out.append(f"<pre><code>{html.escape(body, quote=False)}</code></pre>")
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para()
            level = len(m.group(1))
            title = m.group(2).strip()
            anchor = f"{prefix}-{slug(title)}"
            toc.append((level, title, anchor))
            out.append(f'<h{level} id="{anchor}">{inline(title)}</h{level}>')
            i += 1
            continue
        if line.startswith("|"):
            flush_para()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            cells = "".join(f"<th>{inline(c)}</th>" for c in head)
            out.append(f"<table><thead><tr>{cells}</tr></thead><tbody>")
            for r in body:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            flush_para()
            ordered = m.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines):
                m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if m:
                    items.append(m.group(3))
                    i += 1
                elif lines[i].startswith("  ") and items:  # continuation line
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            out.append(f"<{tag}>" + "".join(f"<li>{inline(t)}</li>" for t in items) + f"</{tag}>")
            continue
        if not line.strip():
            flush_para()
            i += 1
            continue
        para.append(line.strip())
        i += 1
    flush_para()
    return "\n".join(out), toc


STYLE = """
:root {
  --bg: #fbfaf7; --fg: #1f2328; --muted: #5c6670; --line: #d9d4ca;
  --accent: #2f6f4e; --code-bg: #efece5; --th-bg: #efece5;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14161c; --fg: #d8dce3; --muted: #9aa3ad; --line: #2c313a;
    --accent: #8fd3a7; --code-bg: #1e222b; --th-bg: #1e222b;
  }
}
:root[data-theme="dark"] {
  --bg: #14161c; --fg: #d8dce3; --muted: #9aa3ad; --line: #2c313a;
  --accent: #8fd3a7; --code-bg: #1e222b; --th-bg: #1e222b;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.55 var(--sans); }
.wrap { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 32px; max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }
nav { position: sticky; top: 16px; align-self: start; font-size: 14px; max-height: calc(100vh - 32px); overflow: auto; }
nav a { color: var(--muted); text-decoration: none; display: block; padding: 2px 0; }
nav a.l2 { padding-left: 0; } nav a.l3 { padding-left: 14px; font-size: 13px; }
nav a:hover { color: var(--accent); }
nav .part { margin: 14px 0 4px; font-weight: 600; color: var(--fg); }
main { min-width: 0; }
h1 { font-size: 30px; margin: 0 0 6px; } h2 { font-size: 22px; margin: 40px 0 10px; border-bottom: 1px solid var(--line); padding-bottom: 6px; }
h3 { font-size: 17px; margin: 26px 0 8px; }
.subtitle { color: var(--muted); margin: 0 0 20px; }
section.part { margin-top: 56px; }
section.part > h1 { font-size: 24px; color: var(--accent); }
table { border-collapse: collapse; width: 100%; margin: 12px 0 18px; font-size: 14.5px; }
th, td { border: 1px solid var(--line); padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: var(--th-bg); }
code { font: 13.5px var(--mono); background: var(--code-bg); padding: 1px 5px; border-radius: 4px; }
pre { background: var(--code-bg); padding: 12px; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
pre.mermaid { background: none; text-align: center; }
a { color: var(--accent); }
ul, ol { padding-left: 22px; }
li { margin: 3px 0; }
p { margin: 10px 0; }
@media (max-width: 860px) { .wrap { grid-template-columns: 1fr; } nav { position: static; max-height: none; } }
"""


def main() -> None:
    parts, toc_html = [], []
    for fname, label in SOURCES:
        md = (DOCS / fname).read_text()
        prefix = slug(fname.rsplit(".", 1)[0])
        body, toc = convert(md, prefix)
        body = re.sub(r"<h1 id=\"[^\"]+\">.*?</h1>", "", body, count=1)  # file title -> part title
        parts.append(f'<section class="part" id="{prefix}"><h1>{label}</h1>{body}</section>')
        toc_html.append(f'<div class="part"><a href="#{prefix}">{label}</a></div>')
        toc_html += [
            f'<a class="l{lvl}" href="#{anchor}">{inline(title)}</a>'
            for lvl, title, anchor in toc if 2 <= lvl <= 3
        ]
    page = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BubbleBobbleRL report</title>
<style>{STYLE}</style>
<body>
<div class="wrap">
<nav>{''.join(toc_html)}</nav>
<main>
<h1>BubbleBobbleRL: what the agents learned</h1>
<p class="subtitle">Built from <code>docs/*.md</code> by <code>scripts/build_report.py</code>. Diagrams need an internet connection the first time they render.</p>
{''.join(parts)}
</main>
</div>
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({{ startOnLoad: true, theme: dark ? "dark" : "neutral" }});
</script>
</body>
</html>
"""
    out = DOCS / "report.html"
    out.write_text(page)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
