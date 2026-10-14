"""Render the S2 class-strength charts as plain HTML from the CSV snapshots in docs/data.

Each chart replaces a "<!-- chart:NAME -->" marker in the rendered report body.
"""

import csv
import html
from pathlib import Path

DATA = Path(__file__).parent / "docs" / "data" / "s2-strength"

ZH = {
    "전사": "戰士",
    "대검전사": "大劍戰士",
    "검술사": "劍術師",
    "기사": "騎士",
    "궁수": "弓箭手",
    "석궁사수": "弩手",
    "장궁병": "長弓手",
    "마법사": "魔法師",
    "화염술사": "火焰術士",
    "빙결술사": "冰霜術士",
    "전격술사": "電擊術士",
    "힐러": "治癒師",
    "사제": "祭司",
    "수도사": "修道士",
    "암흑술사": "暗黑術士",
    "음유시인": "吟遊詩人",
    "댄서": "舞者",
    "악사": "樂師",
    "도적": "盜賊",
    "격투가": "格鬥家",
    "듀얼블레이드": "雙刀",
}
ROLE_ZH = {"dealer": "輸出", "tank": "坦克", "healer": "治癒"}
ROLE_ORDER = {"dealer": 0, "tank": 1, "healer": 2}
LONG = ["카브락 (어려움)", "에이렐 (매우 어려움)"]


def _read(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load():
    nm = {r["class"]: r for r in _read("mabimobi-nightmare-class.csv")}
    ab = {r["class"]: r for r in _read("mabimobi-abyss-class.csv")}
    ms = _read("mobiscore-dps-by-class.csv")
    role = {c: r["role"].split("(")[0] for c, r in nm.items()}
    return nm, ab, ms, role


def _drill_key(nm):
    return lambda c: (
        -float(nm[c]["top10_avg_zone"]),
        -int(nm[c]["rank100_cut_zone"]),
        float(nm[c]["rank100_cut_sec"]),
    )


def _bars(title, values, fmt, unit_note):
    """Horizontal bar chart; values: list of (class, value)."""
    vmax = max(v for _, v in values)
    rows = []
    group = None
    for c, v in values:
        if _ROLE[c] != group:
            group = _ROLE[c]
            rows.append(f'<div class="bar-group">{ROLE_ZH[group]}</div>')
        pct = 100 * v / vmax
        tip = html.escape(f"{ZH[c]}（{ROLE_ZH[_ROLE[c]]}）：{fmt(v)}")
        rows.append(
            f'<div class="bar-row" title="{tip}"><span class="lbl">{ZH[c]}</span>'
            f'<span class="track"><span class="bar role-{_ROLE[c]}" style="width:{pct:.1f}%"></span>'
            f'<span class="val">{fmt(v)}</span></span></div>'
        )
    return (
        f'<div class="small-multiple"><div class="sm-title">{title}</div>'
        f'<div class="sm-note">{unit_note}</div>{"".join(rows)}</div>'
    )


def chart_sustained(nm, ab, ms, role):
    """Two bar panels: top-10 median DPS on Kabrak (hard) and Eirel (very hard)."""
    panels = []
    for cat, title in zip(LONG, ["卡布拉克 困難", "艾瑞爾 非常困難"]):
        rows = {
            r["class"]: float(r["top10_median"]) for r in ms if r["category"] == cat
        }
        values = sorted(rows.items(), key=lambda kv: (ROLE_ORDER[_ROLE[kv[0]]], -kv[1]))
        panels.append(
            _bars(
                title,
                values,
                lambda v: f"{v / 1e6:.1f}M",
                "前 10 名 DPS 中位數（M = 百萬）",
            )
        )
    return (
        '<figure class="chart"><figcaption>團戰 DPS 排行（모비스코어，2026/09/17～10/14）</figcaption>'
        '<p class="chart-note top">團戰結算依定位分開，所以輸出、坦克、治癒各自排名。</p>'
        f'<div class="sm-grid">{"".join(panels)}</div></figure>'
    )


def chart_drill(nm, ab, ms, role):
    """Nightmare Drill ranking: top-10 average floor as a dot, first-place floor and time beside it."""
    order = sorted(ZH, key=_drill_key(nm))
    lo, hi = 26.0, 30.0
    ticks = [26, 27, 28, 29, 30]

    def x(v):
        return 100 * (v - lo) / (hi - lo)

    rows = []
    for i, c in enumerate(order, 1):
        r = nm[c]
        avg = float(r["top10_avg_zone"])
        tip = html.escape(
            f"{ZH[c]}：前 10 名平均 {avg:.1f} 層；第 1 名 {r['top1_zone']} 層 {r['top1_time']}；"
            f"第 100 名門檻 {r['rank100_cut_zone']} 層 {r['rank100_cut_time']}"
        )
        rows.append(
            f'<div class="dot-row" title="{tip}"><span class="lbl">{i}. {ZH[c]}</span>'
            f'<span class="track"><span class="dot" style="left:{x(avg):.2f}%"></span>'
            f'<span class="val" style="left:{x(avg):.2f}%">{avg:.1f}</span></span>'
            f'<span class="ext">{r["top1_zone"]} 層 {r["top1_time"]}</span></div>'
        )
    axis = "".join(f'<span style="left:{x(v):.2f}%">{v}</span>' for v in ticks)
    step = 100 / (len(ticks) - 1)
    return (
        '<figure class="chart"><figcaption>Nightmare Drill 排行（모비라이프，2026/10/14）</figcaption>'
        '<p class="chart-note top">單人挑戰，結算不分定位，21 個職業一起排名。</p>'
        f'<div class="dots has-ext" style="--gs:{step:.4f}%">'
        '<div class="dot-head"><span class="lbl"></span><span>前 10 名平均層數</span><span class="ext">第 1 名（層、時間）</span></div>'
        f"{''.join(rows)}"
        f'<div class="dot-axis"><span class="lbl"></span><span class="track">{axis}</span><span></span></div></div>'
        '<p class="chart-note">依前 10 名平均層數排序，同層數再比第 100 名的層數與時間。'
        "橫軸從 26 層開始，所有職業都落在 26.4～30.0 層之間。時間如 1:07.21 代表 1 分 7.21 秒。</p></figure>"
    )


_ROLE = {}


def render(body_html):
    """Replace chart markers in the rendered report body."""
    if not DATA.exists():
        return body_html
    nm, ab, ms, role = _load()
    _ROLE.update(role)
    charts = {
        "sustained": chart_sustained,
        "drill": chart_drill,
    }
    for name, fn in charts.items():
        body_html = body_html.replace(f"<!-- chart:{name} -->", fn(nm, ab, ms, role))
    return body_html
