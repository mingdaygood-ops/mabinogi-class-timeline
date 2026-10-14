#!/usr/bin/env python3
"""Build docs/index.html from report.md for GitHub Pages.

Usage: python3 build.py
"""

import html
import re
from pathlib import Path

import markdown
from markdown.extensions.toc import TocExtension

import charts

ROOT = Path(__file__).parent
SRC = ROOT / "report.md"
OUT_DIR = ROOT / "docs"
OUT = OUT_DIR / "index.html"


def slugify(value, separator="-"):
    value = re.sub(r"[（）()／/、，,。：:「」【】\s]+", separator, value.strip())
    return value.strip(separator).lower()


TYPE_CLASSES = {
    "增強": "t-up",
    "削弱": "t-down",
    "有增有減": "t-mixed",
    "其他": "t-note",
}


def type_class(text):
    return TYPE_CLASSES.get(text.strip(), "")


MATRIX_ID = "改版總覽"
CELL = {
    "增強": ("c-up", "▲"),
    "削弱": ("c-down", "▼"),
    "有增有減": ("c-mixed", "◆"),
    "其他": ("c-fix", "·"),
}


def combine(types):
    """Pick one overall direction for all rows a class got on one date."""
    t = set(types)
    if "有增有減" in t or {"增強", "削弱"} <= t:
        return "有增有減"
    for k in ("增強", "削弱"):
        if k in t:
            return k
    return "其他"


def build_matrix(md_text, toc_tokens):
    """Render a class x patch-date overview table from the change tables."""
    ids = {}
    for tok in toc_tokens:
        ids[tok["name"]] = tok["id"]
        for c in tok.get("children", []):
            ids[c["name"]] = c["id"]
    rows, order, group_of, season_of = {}, [], {}, {}
    group = section = None
    for line in md_text.splitlines():
        if line.startswith("## "):
            group, section = line[3:].strip(), None
            if group == "全職業共通變動":
                section = group
                order.append(section)
            continue
        if line.startswith("### "):
            section = line[4:].strip()
            order.append(section)
            group_of[section] = group
            continue
        m = re.match(r"^\| (20\d\d/\d\d/\d\d) \((S\d)\) \| ([^|]+?) \|", line)
        if m and section:
            rows.setdefault(section, {}).setdefault(m.group(1), []).append(m.group(3))
            season_of[m.group(1)] = m.group(2)
    dates = sorted(season_of)
    season_cols = []
    for d in dates:
        if not season_cols or season_cols[-1][0] != season_of[d]:
            season_cols.append([season_of[d], 0])
        season_cols[-1][1] += 1
    starts = {
        d
        for i, d in enumerate(dates)
        if i == 0 or season_of[d] != season_of[dates[i - 1]]
    }

    head = (
        '<tr class="season"><th class="cls"></th>'
        + "".join(f'<th colspan="{n}">{s}</th>' for s, n in season_cols)
        + "</tr>"
    )
    head += (
        '<tr class="dates"><th class="cls"></th>'
        + "".join(f"<th>{d[2:]}</th>" for d in dates)
        + "</tr>"
    )
    body, last_group = [], None
    for name in order:
        g = group_of.get(name)
        if g and g != last_group:
            body.append(
                f'<tr><th class="grp" colspan="{len(dates) + 1}"><span>{html.escape(g)}</span></th></tr>'
            )
            last_group = g
        label = name.split("（")[0]
        cells = []
        for d in dates:
            cls_attr = ' class="s-start"' if d in starts else ""
            types = rows.get(name, {}).get(d)
            if not types:
                cells.append(f"<td{cls_attr}></td>")
                continue
            kind = combine(types)
            css, glyph = CELL[kind]
            extra = " s-start" if d in starts else ""
            tip = html.escape(f"{label} {d}：{'、'.join(types)}")
            cells.append(
                f'<td class="{css}{extra}"><a href="#{ids[name]}" title="{tip}">{glyph}</a></td>'
            )
        body.append(
            f'<tr><th class="cls"><a href="#{ids[name]}">{html.escape(label)}</a></th>{"".join(cells)}</tr>'
        )
    legend = "".join(
        f'<span><i class="{CELL[k][0]}"></i>{k}</span>'
        for k in ("增強", "有增有減", "削弱", "其他")
    )
    return (
        f'<section class="panel" id="{MATRIX_ID}" data-title="{MATRIX_ID}">'
        f"<h2>{MATRIX_ID}</h2>"
        "<p>每一格是該職業在那次改版的整體方向，同一天同時有增強與削弱時算有增有減。"
        "點格子或職業名稱可跳到該職業的分頁；滑鼠停在格子上可看到當天的類型。</p>"
        f'<div class="legend">{legend}</div>'
        f'<table class="matrix"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>'
        "</section>"
    )


def build_panels(body_html, toc_tokens):
    """Split the body into one tab panel per section.

    An h2 with h3 children is a class group: it only becomes a nav label, and
    each h3 under it becomes a panel. Any other h2 becomes a panel itself.
    Returns (panels_html, nav_html).
    """
    groups = {t["id"]: t for t in toc_tokens if t.get("children")}
    parts = re.split(r'(<h([23]) id="([^"]+)">(.*?)</h\2>)', body_html, flags=re.S)
    # parts: [preamble, full_heading, level, id, inner, content, full_heading, ...]
    panels = []
    group_name = ""
    for i in range(1, len(parts), 5):
        _, level, hid, inner, content = parts[i : i + 5]
        if level == "2" and hid in groups:
            group_name = groups[hid]["name"]
            continue
        if level == "2":
            group_name = ""
        kicker = (
            f'<p class="kicker">{html.escape(group_name)}</p>' if group_name else ""
        )
        panels.append(
            f'<section class="panel" id="{hid}" data-title="{html.escape(re.sub("<[^>]+>", "", inner))}">'
            f"{kicker}<h2>{inner}</h2>{content}</section>"
        )

    nav_items = []
    for tok in toc_tokens:
        if tok["id"] in groups:
            children = "".join(
                f'<li><a href="#{c["id"]}">{html.escape(c["name"])}</a></li>'
                for c in tok["children"]
            )
            nav_items.append(
                f'<li class="group"><span>{html.escape(tok["name"])}</span><ul>{children}</ul></li>'
            )
        else:
            nav_items.append(
                f'<li><a href="#{tok["id"]}">{html.escape(tok["name"])}</a></li>'
            )
    return "\n".join(panels), "<ul>" + "".join(nav_items) + "</ul>"


def main():
    md_text = SRC.read_text(encoding="utf-8")
    lines = md_text.splitlines()
    title = lines[0].lstrip("# ").strip()
    # The "last updated" line moves from the body into the page header.
    updated_re = re.compile(r"^最後更新：(\d{4}/\d{2}/\d{2})$")
    updated = next((m.group(1) for m in map(updated_re.match, lines) if m), None)
    if not updated:
        raise SystemExit("report.md needs a line like '最後更新：2026/10/14'")
    body_lines = [line for line in lines[1:] if not updated_re.match(line)]
    body_md = "\n".join(body_lines)

    md = markdown.Markdown(
        extensions=[
            "tables",
            "md_in_html",
            TocExtension(slugify=slugify, toc_depth="2-3"),
        ]
    )
    body_html = md.convert(body_md)
    body_html = charts.render(body_html)

    # Open external links in a new tab.
    body_html = body_html.replace(
        '<a href="http', '<a target="_blank" rel="noopener" href="http'
    )

    # Render the 類型 column (2nd cell of 4-column tables) as a coloured badge.
    def tag_row(m):
        cells = re.findall(r"<td>(.*?)</td>", m.group(0), flags=re.S)
        if len(cells) == 4 and re.sub("<[^>]+>", "", cells[1]).strip() in TYPE_CLASSES:
            cls = type_class(re.sub("<[^>]+>", "", cells[1]))
            row = m.group(0).replace(
                f"<td>{cells[1]}</td>",
                f'<td class="type"><span class="badge {cls}">{cells[1]}</span></td>',
                1,
            )
            return row
        return m.group(0)

    body_html = re.sub(r"<tr>.*?</tr>", tag_row, body_html, flags=re.S)
    # Change-log tables (those with a type column) get their own layout rules.
    body_html = re.sub(
        r"<table>(?=(?:(?!</table>).)*?class=\"type\")",
        '<table class="changes">',
        body_html,
        flags=re.S,
    )

    # Skill names 【...】 and accessory-rune variants 〔...〕 become coloured chips.
    body_html = re.sub(
        r"【[^【】]+】", lambda m: f'<span class="sk">{m.group(0)}</span>', body_html
    )
    body_html = re.sub(
        r"〔[^〔〕]+〕", lambda m: f'<span class="rn">{m.group(0)}</span>', body_html
    )

    # Season summary bullets: "S0（period）：text" -> season badge + period label.
    body_html = re.sub(
        r"<li>(S[0-2])（([^）]*)）：",
        r'<li><div class="s-head"><span class="s-tag">\1</span><span class="s-period">\2</span></div>',
        body_html,
    )
    body_html = body_html.replace(
        '<ul>\n<li><div class="s-head">',
        '<ul class="seasons">\n<li><div class="s-head">',
    )

    # Community commentary block: "社群評論：" paragraph followed by a list or a one-line note.
    body_html = body_html.replace(
        "<p>社群評論：</p>\n<ul>",
        '<p class="community-label">社群評論</p>\n<ul class="community">',
    )
    body_html = re.sub(
        r"<p>社群評論：(.+?)</p>",
        r'<p class="community-label">社群評論</p>\n<p class="community-none">\1</p>',
        body_html,
    )

    panels_html, nav_html = build_panels(body_html, md.toc_tokens)

    # The overview matrix goes right after the first panel (usage notes).
    matrix = build_matrix(md_text, md.toc_tokens)
    first_end = panels_html.index("</section>") + len("</section>")
    panels_html = panels_html[:first_end] + "\n" + matrix + panels_html[first_end:]
    first_li = nav_html.index("</li>") + len("</li>")
    nav_html = (
        nav_html[:first_li]
        + f'<li><a href="#{MATRIX_ID}">{MATRIX_ID}</a></li>'
        + nav_html[first_li:]
    )

    template = (ROOT / "template.html").read_text(encoding="utf-8")
    page = (
        template.replace("{{TITLE}}", html.escape(title))
        .replace("{{UPDATED}}", updated)
        .replace("{{NAV}}", nav_html)
        .replace("{{BODY}}", panels_html)
    )
    OUT_DIR.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
