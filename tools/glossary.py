#!/usr/bin/env python3
"""Extract the Chinese-Korean name pairs already used in report.md.

Usage:
  python3 tools/glossary.py                 # print all pairs as TSV, then conflicts
  python3 tools/glossary.py --lookup 꿰뚫기  # look up a Korean or Chinese name
  python3 tools/glossary.py --conflicts     # only conflicts; exit 1 if any

Kinds: skill = 【中文（韓文）】, rune = 〔中文（韓文）〕, quoted = 「中文（韓文）」,
plain = 中文（韓文） written without brackets.
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANGUL = r"[가-힣]"
PATTERNS = [
    ("skill", re.compile(rf"【([^【】（）]+)（({HANGUL}[^（）]*)）】")),
    ("rune", re.compile(rf"〔([^〔〕（）]+)（({HANGUL}[^（）]*)）〕")),
    ("quoted", re.compile(rf"「([^「」（）]+)（({HANGUL}[^（）]*)）」")),
    ("plain", re.compile(rf"([一-鿿][一-鿿0-9+：:]{{0,15}})（({HANGUL}[^（）]*)）")),
]


def collect(text):
    """Return {(kind, korean, chinese): count}."""
    pairs = defaultdict(int)
    for kind, pat in PATTERNS:
        for zh, ko in pat.findall(text):
            pairs[(kind, ko.strip(), zh.strip())] += 1
    return pairs


def conflicts(pairs):
    """Korean terms written with more than one Chinese name (any kind).

    Plain captures cannot tell where a name starts, so a name that ends with
    another captured name of the same Korean term (for example 無法發動夜之祝福
    and 夜之祝福) counts as the same name.
    """
    by_ko = defaultdict(set)
    for (_, ko, zh), _n in pairs.items():
        by_ko[ko].add(zh)
    out = {}
    for ko, zhs in by_ko.items():
        core = {z for z in zhs if not any(z != o and z.endswith(o) for o in zhs)}
        # All captures sharing a common ending of 2+ characters are one name too.
        common = os.path.commonprefix([z[::-1] for z in core])[::-1]
        if len(core) > 1 and len(common) < 2:
            out[ko] = sorted(core)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", default=str(ROOT / "report.md"))
    ap.add_argument("--lookup", help="Korean or Chinese name to look up")
    ap.add_argument("--conflicts", action="store_true", help="only print conflicts")
    args = ap.parse_args()

    pairs = collect(Path(args.report).read_text(encoding="utf-8"))
    bad = conflicts(pairs)

    if args.lookup:
        hits = [
            (k, ko, zh, n)
            for (k, ko, zh), n in pairs.items()
            if args.lookup in (ko, zh) or args.lookup in ko
        ]
        for k, ko, zh, n in sorted(hits):
            print(f"{k}\t{ko}\t{zh}\t{n}")
        if not hits:
            print(f"no existing name for {args.lookup}")
        return

    if not args.conflicts:
        print("kind\tkorean\tchinese\tcount")
        for (k, ko, zh), n in sorted(
            pairs.items(), key=lambda kv: (kv[0][0], kv[0][1])
        ):
            print(f"{k}\t{ko}\t{zh}\t{n}")
    if bad:
        print(
            f"\n{len(bad)} Korean terms with more than one Chinese name:",
            file=sys.stderr,
        )
        for ko, zhs in sorted(bad.items()):
            print(f"  {ko}: {' / '.join(zhs)}", file=sys.stderr)
        if args.conflicts:
            sys.exit(1)
    elif args.conflicts:
        print(f"no conflicts among {len({ko for _, ko, _ in pairs})} Korean terms")


if __name__ == "__main__":
    main()
