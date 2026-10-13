#!/usr/bin/env python3
"""Build docs/index.html from report.md for GitHub Pages.

Usage: python3 build.py
"""
import html
import re
from pathlib import Path

import markdown
from markdown.extensions.toc import TocExtension

ROOT = Path(__file__).parent
SRC = ROOT / "report.md"
OUT_DIR = ROOT / "docs"
OUT = OUT_DIR / "index.html"


def slugify(value, separator="-"):
    value = re.sub(r"[（）()／/、，,。：:「」【】\s]+", separator, value.strip())
    return value.strip(separator).lower()


def type_class(text):
    t = text.strip()
    if t.startswith("修↑"):
        return "t-fixup"
    if t.startswith("修↓"):
        return "t-fixdown"
    if t.startswith("修"):
        return "t-fix"
    if t.startswith("↑"):
        return "t-up"
    if t.startswith("↓"):
        return "t-down"
    if t.startswith("↔"):
        return "t-mixed"
    if t.startswith("新"):
        return "t-new"
    if t.startswith("說"):
        return "t-note"
    return ""


def main():
    md_text = SRC.read_text(encoding="utf-8")
    lines = md_text.splitlines()
    title = lines[0].lstrip("# ").strip()
    # Drop the title and the byline (date · author) from the body; the page header carries them.
    body_lines = lines[1:]
    body_lines = [l for l in body_lines if not re.match(r"^\w{3} \d{1,2}, \d{4} ·", l)]
    body_md = "\n".join(body_lines)

    md = markdown.Markdown(
        extensions=["tables", TocExtension(slugify=slugify, toc_depth="2-3")]
    )
    body_html = md.convert(body_md)

    # Open external links in a new tab.
    body_html = body_html.replace('<a href="http', '<a target="_blank" rel="noopener" href="http')

    # Tag the 類型 column (2nd cell of 4-column tables) with a class for colour.
    def tag_row(m):
        cells = re.findall(r"<td>(.*?)</td>", m.group(0), flags=re.S)
        if len(cells) == 4:
            cls = type_class(re.sub("<[^>]+>", "", cells[1]))
            row = m.group(0).replace(
                f"<td>{cells[1]}</td>", f'<td class="type {cls}">{cells[1]}</td>', 1
            )
            return row
        return m.group(0)

    body_html = re.sub(r"<tr>.*?</tr>", tag_row, body_html, flags=re.S)

    # Sidebar navigation from h2/h3.
    nav_items = []
    for tok in md.toc_tokens:
        children = "".join(
            f'<li><a href="#{c["id"]}">{html.escape(c["name"])}</a></li>'
            for c in tok.get("children", [])
        )
        sub = f"<ul>{children}</ul>" if children else ""
        nav_items.append(f'<li><a href="#{tok["id"]}">{html.escape(tok["name"])}</a>{sub}</li>')
    nav_html = "<ul>" + "".join(nav_items) + "</ul>"

    template = (ROOT / "template.html").read_text(encoding="utf-8")
    page = (
        template.replace("{{TITLE}}", html.escape(title))
        .replace("{{NAV}}", nav_html)
        .replace("{{BODY}}", body_html)
    )
    OUT_DIR.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
