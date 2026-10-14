#!/usr/bin/env python3
"""Consistency checks for report.md. Exit code 1 when any check fails.

Usage: python3 tools/check_report.py [path/to/report.md]
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "report.md"

TYPES = {"增強", "削弱", "有增有減", "其他"}
NOTICE = r"https://mabinogimobile\.nexon\.com/News/Update/(\d+)"
ROW = re.compile(
    rf"^\| (20\d\d/\d\d/\d\d) \((S\d)\) \| ([^|]+?) \|(.*)\| \[([^\]]+)\]\({NOTICE}\) \|$"
)
HANGUL = re.compile(r"[가-힣]")
# Words that must not come back after earlier renames; "討論區", "換區" and "冰封區" are fine.
BANNED = {
    "修正後變強": "type labels are 增強／削弱／有增有減／其他",
    "修正後變弱": "type labels are 增強／削弱／有增有減／其他",
    "深淵地獄": "Nightmare Drill keeps its English name; 深淵 is the Abyss dungeon",
    "連携": "use 連攜",
    "꾰뚫기": "typo of 꿰뚫기",
    "포춈": "typo of 포츈",
}
BANNED_RE = {
    r"(?<!Nightmare )Drill": "write the full name Nightmare Drill",
    r"\d 區": "Nightmare Drill is counted in 層, not 區",
}


def season(date):
    """Season by the date a change went live."""
    if date < "2025/09/25":
        return "S0"
    if date < "2026/06/25":
        return "S1"
    return "S2"


def main():
    text = REPORT.read_text(encoding="utf-8")
    lines = text.split("\n")
    problems = defaultdict(list)

    # Official notice id per date, from the sources table.
    sources = {}
    for line in lines:
        m = re.match(rf"^\| (20\d\d/\d\d/\d\d) \| \[[^\]]*\]\({NOTICE}\)", line)
        if m:
            sources[m.group(1)] = m.group(2)

    rows = 0
    for i, line in enumerate(lines, 1):
        if not re.match(r"^\| 20\d\d/\d\d/\d\d \(S", line):
            continue
        m = ROW.match(line)
        if not m:
            problems["change row does not parse"].append(i)
            continue
        rows += 1
        date, tag, typ, content, label, nid = m.groups()
        if season(date) != tag:
            problems["season tag does not match date"].append(f"{i}: {date} {tag}")
        if typ not in TYPES:
            problems["unknown type"].append(f"{i}: {typ}")
        if sources.get(date) != nid:
            problems["notice link differs from sources table"].append(f"{i}: {date}")
        if label != f"{int(date[5:7])}/{int(date[8:10])}":
            problems["link label does not match date"].append(f"{i}: {label}")
        if not content.strip():
            problems["empty content"].append(i)

    # Every row date must be listed in the sources table.
    for date in sorted(set(re.findall(r"(?m)^\| (20\d\d/\d\d/\d\d) \(S", text))):
        if date not in sources:
            problems["date missing from sources table"].append(date)

    # Class sections: three season bullets and a community block.
    heads = [m for m in re.finditer(r"(?m)^### (.+)$", text)]
    end = text.index("## 來源清單")
    for k, m in enumerate(heads):
        block = text[m.start() : heads[k + 1].start() if k + 1 < len(heads) else end]
        if len(re.findall(r"(?m)^- S[012]（", block)) != 3:
            problems["class section needs S0/S1/S2 bullets"].append(m.group(1))
        if "社群評論" not in block:
            problems["class section has no 社群評論 block"].append(m.group(1))

    # Brackets must pair up.
    for a, b in ("【】", "〔〕", "「」", "（）"):
        if text.count(a) != text.count(b):
            problems["unbalanced brackets"].append(
                f"{a}{b} {text.count(a)}/{text.count(b)}"
            )

    # Korean must sit inside （） right after a Chinese name (link URLs excluded).
    stripped = re.sub(r"\]\([^)]*\)", "]", text)
    for _ in range(3):
        stripped = re.sub(r"（[^（）]*）", "", stripped)
    for i, line in enumerate(stripped.split("\n"), 1):
        if HANGUL.search(line) and not line.startswith("#"):
            problems["Korean outside （）"].append(line[:60])

    for word, why in BANNED.items():
        for i, line in enumerate(lines, 1):
            if word in line:
                problems[f"banned word {word} ({why})"].append(i)
    for pat, why in BANNED_RE.items():
        for i, line in enumerate(lines, 1):
            if re.search(pat, line):
                problems[f"pattern {pat} ({why})"].append(i)

    if not re.search(r"(?m)^最後更新：\d{4}/\d{2}/\d{2}$", text):
        problems["missing 最後更新：YYYY/MM/DD line"].append("report.md line 3")

    print(
        f"{REPORT.name}: {rows} change rows, {len(sources)} sources, {len(heads)} class sections"
    )
    if problems:
        for name, items in problems.items():
            print(f"FAIL {name}: {items[:10]}")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
