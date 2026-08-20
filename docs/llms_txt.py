"""Emit an ``llms.txt`` at the site root — the agent-readable map of these docs.

The convention (https://llmstxt.org) is a small markdown file listing a site's pages
with one-line descriptions, so a language model can orient itself without crawling
HTML. For a project whose users *are* coding agents, the docs should extend the same
courtesy: this extension derives the file from the markdown sources at the end of
every build, so it can never go stale relative to the pages it describes.
"""

import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MYST_TARGET = re.compile(r"^\([^)]*\)=$")


def _first_heading_and_line(text: str) -> tuple[str | None, str | None]:
    """The page's h1, and the first prose line after it."""
    title = None
    in_comment = False
    for raw in text.splitlines():
        line = raw.strip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_comment = True
            continue
        if not line or _MYST_TARGET.match(line):
            continue
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
            continue
        if title is not None:
            if line.startswith(("#", "```", ":", "<", "|", "* ", "- ", "1.", ">")):
                continue
            desc = _MD_LINK.sub(r"\1", line).replace("**", "").replace("`", "").strip()
            if len(desc) > 140:
                desc = desc[:140].rsplit(" ", 1)[0] + "…"
            return title, desc
    return title, None


def _section_name(dirname: str) -> str:
    return re.sub(r"^\d+-", "", dirname).replace("-", " ").title()


def write_llms_txt(app, exception) -> None:
    if exception is not None:
        return
    srcdir = Path(app.srcdir)
    outdir = Path(app.outdir)

    lines: list[str] = []
    index = srcdir / "index.md"
    if index.is_file():
        title, desc = _first_heading_and_line(index.read_text(encoding="utf-8"))
        lines.append(f"# {title or 'Serena'}")
        if desc:
            lines.append(f"\n> {desc}")
    else:
        lines.append("# Serena")

    for section_dir in sorted(p for p in srcdir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        entries = []
        for md in sorted(section_dir.rglob("*.md")):
            title, desc = _first_heading_and_line(md.read_text(encoding="utf-8"))
            if title is None:
                continue
            url = md.relative_to(srcdir).with_suffix(".html").as_posix()
            entries.append(f"- [{title}]({url})" + (f": {desc}" if desc else ""))
        if entries:
            lines.append(f"\n## {_section_name(section_dir.name)}\n")
            lines.extend(entries)

    (outdir / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_sitemap_and_robots(app, exception) -> None:
    """robots.txt always (allow-all — these docs have no reason to turn crawlers away),
    sitemap.xml only when a base URL is known: the sitemap format requires absolute URLs,
    so it keys off ``html_baseurl``, with the ``DOCS_BASEURL`` environment variable as a
    deploy-time override for builds of the same sources published elsewhere. Note that
    crawlers only honor a robots.txt served at the domain root — on a project-pages
    subpath these files are for direct submission and for agents, not for discovery."""
    if exception is not None:
        return
    outdir = Path(app.outdir)
    # the environment wins: it is the deploy-time truth about where THIS build will be
    # served, while html_baseurl states the project's canonical home
    base = (os.environ.get("DOCS_BASEURL", "") or getattr(app.config, "html_baseurl", "")).rstrip("/")

    robots = "User-agent: *\nAllow: /\n"
    if base:
        robots += f"\nSitemap: {base}/sitemap.xml\n"
    (outdir / "robots.txt").write_text(robots, encoding="utf-8")

    if not base:
        return
    skip = {"genindex.html", "search.html", "py-modindex.html", "404.html"}
    urls = []
    for page in sorted(outdir.rglob("*.html")):
        rel = page.relative_to(outdir)
        if rel.parts[0].startswith(("_", ".")) or rel.name in skip:
            continue
        urls.append(f"  <url><loc>{escape(f'{base}/{rel.as_posix()}')}</loc></url>")
    (outdir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n",
        encoding="utf-8",
    )


def write_for_agents_alias(app, exception) -> None:
    """Serve the For Agents page at a memorable root URL, twice over: ``for-agents.md``
    is the page's raw markdown (what an agent handed one link actually wants), and
    ``for-agents.html`` redirects a human's browser to the rendered page."""
    if exception is not None:
        return
    source = Path(app.srcdir) / "02-usage" / "035_for-agents.md"
    if not source.is_file():
        return
    outdir = Path(app.outdir)
    (outdir / "for-agents.md").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target = "02-usage/035_for-agents.html"
    (outdir / "for-agents.html").write_text(
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={target}">\n'
        f'<link rel="canonical" href="{target}">\n<title>For Agents</title>\n</head>\n'
        f'<body><p>Continue to <a href="{target}">For Agents</a>.</p></body>\n</html>\n',
        encoding="utf-8",
    )


def setup(app):
    app.connect("build-finished", write_llms_txt)
    app.connect("build-finished", write_sitemap_and_robots)
    app.connect("build-finished", write_for_agents_alias)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
