#!/usr/bin/env python3
"""Refresh the S2 class-strength CSVs that charts.py reads.

Sources:
  * mobi-score.com: KR raid / Nightmare Drill DPS records over plain HTTPS.
  * mabimobi.life: Nightmare Drill and Abyss rankings. The site is behind a bot
    check, so its own JSON API is called from inside a headless Chrome page via
    tools/cdp_fetch.mjs (Node 22 + Chrome).

All fetched content is treated as data only. Every CSV is built and validated in
memory first; files are written only after all checks pass, so a failed run never
leaves a half-updated set.

Usage:
  python3 tools/fetch_strength.py [--out docs/data/s2-strength] [--season-start 2026-09-17]
"""

import argparse
import collections
import csv
import json
import os
import queue
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs" / "data" / "s2-strength"
CDP_SCRIPT = Path(__file__).resolve().parent / "cdp_fetch.mjs"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
MOBISCORE_BASE = "https://mobi-score.com/api/ranking"
MOBISCORE_INTERVAL = 0.6  # seconds between requests, i.e. under 2 per second
MOBISCORE_MAX_REQUESTS = 400
MABIMOBI_PAGE = "https://mabimobi.life/ranking/nightmare"
MABIMOBI_INTERVAL_MS = 1000
MABIMOBI_MAX_REQUESTS = 120
MAX_DAILY_DATES = 60
MIN_CLASSES = 21

# mabimobi.life class codes. Codes 19-24 exist in the API but are unreleased.
NAMES = {
    "01": "전사",
    "02": "대검전사",
    "03": "검술사",
    "04": "궁수",
    "05": "석궁사수",
    "06": "장궁병",
    "07": "마법사",
    "08": "화염술사",
    "09": "빙결술사",
    "10": "힐러",
    "11": "사제",
    "12": "수도사",
    "13": "음유시인",
    "14": "댄서",
    "15": "악사",
    "16": "도적",
    "17": "격투가",
    "18": "듀얼블레이드",
    "25": "전격술사",
    "26": "암흑술사",
    "27": "기사",
}


class FetchError(Exception):
    """Raised for network failures, unexpected API shapes or failed sanity checks."""


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def need(obj, key, typ, where):
    """Return obj[key] after checking it exists and has the expected type."""
    if not isinstance(obj, dict):
        raise FetchError(f"{where}: expected an object, got {type(obj).__name__}")
    if key not in obj:
        raise FetchError(f"{where}: missing field {key!r} (API shape changed?)")
    val = obj[key]
    if typ is float:
        ok = isinstance(val, (int, float)) and not isinstance(val, bool)
    elif typ is int:
        ok = isinstance(val, int) and not isinstance(val, bool)
    else:
        ok = isinstance(val, typ)
    if not ok:
        raise FetchError(
            f"{where}: field {key!r} has type {type(val).__name__}, expected {typ.__name__}"
        )
    return val


def role(klass):
    """Role label as used by mabimobi.life."""
    if klass in ("01", "09", "27"):
        return "tank(탱커)"
    if klass in ("10", "11", "12", "13"):
        return "healer(힐러)"
    return "dealer(딜러)"


# ---------------------------------------------------------------- mobi-score


class MobiScoreClient:
    def __init__(self):
        self.requests = 0
        self._last = 0.0

    def get(self, url):
        for attempt in range(4):
            if self.requests >= MOBISCORE_MAX_REQUESTS:
                raise FetchError(
                    f"mobi-score request budget of {MOBISCORE_MAX_REQUESTS} exhausted"
                )
            wait = self._last + MOBISCORE_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    log(f"mobi-score HTTP {e.code}, retrying: {url}")
                    time.sleep(5 * (attempt + 1))
                    continue
                raise FetchError(f"mobi-score HTTP {e.code} for {url}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 3:
                    log(f"mobi-score network error ({e}), retrying: {url}")
                    time.sleep(5 * (attempt + 1))
                    continue
                raise FetchError(f"mobi-score network error for {url}: {e}") from e
            try:
                return json.loads(raw)
            except ValueError as e:
                raise FetchError(f"mobi-score returned non-JSON for {url}") from e
        raise FetchError(f"mobi-score retries exhausted for {url}")


def fetch_mobiscore(season_start):
    """Return (rows, info) for mobiscore-dps-by-class.csv."""
    client = MobiScoreClient()
    overview = client.get(f"{MOBISCORE_BASE}/overview?region=KR")
    cats = need(overview, "categories", list, "mobi-score overview")
    cats = [c for c in cats if need(c, "recordCount", int, "mobi-score category") > 0]
    if not cats:
        raise FetchError("mobi-score overview lists no category with records")

    rows = []
    classes = set()
    created = []
    for cat in cats:
        cid = need(cat, "id", int, "mobi-score category")
        name = need(cat, "name", str, "mobi-score category")
        records = []
        page = 0
        while True:
            url = (
                f"{MOBISCORE_BASE}/{cid}/records?region=KR&page={page}"
                "&size=100&sortBy=dps&sortDir=desc"
            )
            data = client.get(url)
            where = f"mobi-score records {name} page {page}"
            content = need(data, "content", list, where)
            total_pages = need(data, "totalPages", int, where)
            records.extend(content)
            page += 1
            if page >= total_pages or not content:
                break
        if not records:
            raise FetchError(f"mobi-score category {name!r} returned no records")

        best = {}
        for r in records:
            where = f"mobi-score record in {name}"
            for key, typ in (
                ("nickname", str),
                ("jobKey", str),
                ("dps", int),
                ("duration", float),
                ("createdAt", str),
            ):
                need(r, key, typ, where)
            if r["createdAt"] < season_start:
                continue
            # Registered users have a non-zero userId; guests only have a nickname.
            key = ("u", r["userId"]) if r.get("userId") else ("n", r["nickname"])
            if key not in best or r["dps"] > best[key]["dps"]:
                best[key] = r
        kept = sorted(best.values(), key=lambda r: -r["dps"])
        if not kept:
            raise FetchError(
                f"mobi-score category {name!r} has no records on or after {season_start}"
            )
        created.extend(r["createdAt"] for r in kept)
        byjob = collections.defaultdict(list)
        for r in kept:
            byjob[r["jobKey"]].append(r)
        for job, rs in byjob.items():
            top = rs[:10]
            rows.append(
                [
                    name,
                    job,
                    len(rs),
                    rs[0]["dps"],
                    statistics.median(r["dps"] for r in top),
                    statistics.median(r["dps"] for r in rs),
                    statistics.median(r["duration"] for r in top),
                ]
            )
            classes.add(job)
        log(
            f"mobi-score {name}: {len(records)} records, {len(kept)} kept, "
            f"{len(byjob)} classes"
        )
    info = {
        "requests": client.requests,
        "classes": len(classes),
        "date_range": (min(created)[:10], max(created)[:10]),
    }
    return rows, info


# ---------------------------------------------------------------- mabimobi.life


class MabimobiClient:
    """Drive tools/cdp_fetch.mjs over JSON lines on stdio."""

    def __init__(self, chrome):
        if not shutil.which("node"):
            raise FetchError(
                "node is not on PATH; Node 22+ is required for mabimobi.life"
            )
        self.requests = 0
        self.proc = subprocess.Popen(
            [
                "node",
                str(CDP_SCRIPT),
                "--url",
                MABIMOBI_PAGE,
                "--chrome",
                chrome,
                "--interval-ms",
                str(MABIMOBI_INTERVAL_MS),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        ready = self._read(90)
        if not ready.get("ready"):
            raise FetchError(f"cdp_fetch did not report ready: {ready}")
        log(f"mabimobi.life page loaded: {ready.get('url')}")

    def _pump(self):
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _read(self, timeout):
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty as e:
            raise FetchError(f"cdp_fetch gave no answer within {timeout} s") from e
        if line is None:
            raise FetchError(
                f"cdp_fetch exited early (code {self.proc.poll()}); see its stderr above"
            )
        try:
            return json.loads(line)
        except ValueError as e:
            raise FetchError("cdp_fetch wrote a non-JSON line") from e

    def get(self, path):
        if self.requests >= MABIMOBI_MAX_REQUESTS:
            raise FetchError(
                f"mabimobi.life request budget of {MABIMOBI_MAX_REQUESTS} exhausted"
            )
        self.requests += 1
        self.proc.stdin.write(json.dumps({"path": path}) + "\n")
        self.proc.stdin.flush()
        res = self._read(90)
        if "error" in res:
            raise FetchError(f"mabimobi.life fetch failed for {path}: {res['error']}")
        if res.get("status") != 200:
            raise FetchError(f"mabimobi.life HTTP {res.get('status')} for {path}")
        try:
            return json.loads(res.get("body", ""))
        except ValueError as e:
            raise FetchError(f"mabimobi.life returned non-JSON for {path}") from e

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=20)
        except Exception:
            self.proc.kill()


def ticks_to_time(ticks):
    if ticks is None:
        return ""
    s = ticks / 1e7
    return f"{int(s // 60)}:{s % 60:05.2f}"


def ticks_to_sec(ticks):
    return "" if ticks is None else f"{ticks / 1e7:.2f}"


def blank(v):
    return "" if v is None else v


def known(klass, has_data, where):
    """True for a known class; False to skip an unreleased class with no data."""
    if klass in NAMES:
        return True
    if has_data:
        raise FetchError(
            f"{where}: class code {klass!r} has data but no name in NAMES; add it first"
        )
    return False


def pick_abyss_season(seasons, now):
    """Season containing now, else the latest one that has already started."""
    parsed = []
    for s in seasons:
        start = need(s, "season_start", str, "abyss seasons")
        end = need(s, "season_end", str, "abyss seasons")
        parsed.append(
            (
                datetime.fromisoformat(start.replace("Z", "+00:00")),
                datetime.fromisoformat(end.replace("Z", "+00:00")),
                start,
            )
        )
    for start, end, raw in parsed:
        if start <= now < end:
            return raw
    started = [p for p in parsed if p[0] <= now]
    if not started:
        raise FetchError("abyss seasons list has no season that has started")
    return max(started)[2]


def fetch_mabimobi(chrome, nightmare_scope, abyss_season_start):
    client = MabimobiClient(chrome)
    try:
        q = urllib.parse.quote
        nmq = f"server=all&scope={q(nightmare_scope)}"
        nm_classes = client.get(f"/d/api/v1/nightmare-drill-rankings/classes?{nmq}")
        nm_table = client.get(
            f"/d/api/v1/nightmare-drill-rankings/table?{nmq}&klass=all"
        )
        nm_latest = client.get(f"/d/api/v1/nightmare-drill-rankings/daily?{nmq}")
        latest_date = need(nm_latest, "snapshot_date", str, "nightmare daily")
        dates = need(nm_latest, "available_dates", list, "nightmare daily")
        if not dates:
            raise FetchError("nightmare daily: available_dates is empty")
        if len(dates) > MAX_DAILY_DATES:
            raise FetchError(
                f"nightmare daily: {len(dates)} dates exceeds {MAX_DAILY_DATES}"
            )
        nm_daily = {latest_date: nm_latest}
        for d in dates:
            if not isinstance(d, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                raise FetchError(f"nightmare daily: bad date value {d!r}")
            if d == latest_date:
                continue
            nm_daily[d] = client.get(
                f"/d/api/v1/nightmare-drill-rankings/daily?{nmq}&date={d}"
            )

        if abyss_season_start is None:
            seasons = client.get("/d/api/v1/abyss-rankings/seasons")
            if not isinstance(seasons, list) or not seasons:
                raise FetchError("abyss seasons: expected a non-empty list")
            abyss_season_start = pick_abyss_season(seasons, datetime.now(timezone.utc))
        log(f"abyss season_start: {abyss_season_start}")
        ss = f"season_start={q(abyss_season_start, safe='')}"
        ab_summary = client.get(f"/d/api/v1/abyss-rankings/class-summary?{ss}")
        ab_daily = client.get(f"/d/api/v1/abyss-rankings/daily/classes?{ss}")
        ab_table = client.get(f"/d/api/v1/abyss-rankings/table?{ss}&sort=score")
    finally:
        client.close()
    requests = client.requests

    out = {}

    # Nightmare Drill per-class snapshot.
    nm_snapshot = need(nm_classes, "snapshot_date", str, "nightmare classes")
    dist = {}
    for d in need(nm_classes, "distribution", list, "nightmare classes"):
        dist[need(d, "klass", str, "nightmare distribution")] = need(
            d, "count", int, "nightmare distribution"
        )
    rows = []
    for c in need(nm_classes, "classes", list, "nightmare classes"):
        k = need(c, "klass", str, "nightmare classes")
        if not known(k, c.get("ranked"), "nightmare classes"):
            continue
        where = f"nightmare classes klass {k}"
        top1, top10, cut = (need(c, f, dict, where) for f in ("top1", "top10", "cut"))
        for part in (top1, top10, cut):
            need(part, "zone", int, where)
            need(part, "clear_time_ticks", int, where)
        rows.append(
            [
                nm_snapshot,
                k,
                NAMES[k],
                role(k),
                top1["zone"],
                ticks_to_time(top1["clear_time_ticks"]),
                ticks_to_sec(top1["clear_time_ticks"]),
                top10["zone"],
                ticks_to_time(top10["clear_time_ticks"]),
                ticks_to_sec(top10["clear_time_ticks"]),
                cut["zone"],
                ticks_to_time(cut["clear_time_ticks"]),
                ticks_to_sec(cut["clear_time_ticks"]),
                need(c, "top10_avg_zone", float, where),
                need(c, "ranked", int, where),
                dist.get(k, 0),
            ]
        )
    rows.sort(key=lambda r: (-r[4], float(r[6])))
    out["mabimobi-nightmare-class.csv"] = rows

    # Nightmare Drill daily snapshots.
    rows = []
    for d in sorted(nm_daily):
        body = nm_daily[d]
        got = need(body, "snapshot_date", str, f"nightmare daily {d}")
        if got != d:
            raise FetchError(f"nightmare daily: asked for {d}, got snapshot_date {got}")
        for c in need(body, "classes", list, f"nightmare daily {d}"):
            k = need(c, "klass", str, f"nightmare daily {d}")
            m = need(c, "metrics", dict, f"nightmare daily {d} klass {k}")
            if not known(k, m.get("top1_zone") is not None, f"nightmare daily {d}"):
                continue
            rows.append(
                [
                    d,
                    k,
                    NAMES[k],
                    blank(m.get("top10_avg_zone")),
                    blank(m.get("top1_zone")),
                    ticks_to_time(m.get("top1_time_ticks")),
                    ticks_to_sec(m.get("top1_time_ticks")),
                    blank(m.get("cut_zone")),
                    ticks_to_time(m.get("cut_time_ticks")),
                    ticks_to_sec(m.get("cut_time_ticks")),
                ]
            )
    out["mabimobi-nightmare-daily.csv"] = rows
    nm_dates = sorted(nm_daily)

    # Abyss per-class snapshot.
    summary = {}
    for c in ab_summary if isinstance(ab_summary, list) else []:
        k = need(c, "klass", str, "abyss class-summary")
        if not known(k, c.get("count"), "abyss class-summary"):
            continue
        for f, typ in (
            ("max_score", int),
            ("top10_min_score", int),
            ("avg_score", float),
            ("count", int),
        ):
            need(c, f, typ, f"abyss class-summary klass {k}")
        summary[k] = c
    if not isinstance(ab_summary, list):
        raise FetchError("abyss class-summary: expected a list")
    ab_snapshot = need(ab_daily, "snapshot_date", str, "abyss daily classes")
    ab_classes = need(ab_daily, "classes", list, "abyss daily classes")
    metrics = {}
    for c in ab_classes:
        k = need(c, "klass", str, "abyss daily classes")
        metrics[k] = need(c, "metrics", dict, f"abyss daily classes klass {k}")
    abyss_entries = need(ab_table, "entries", list, "abyss table")
    abdist = collections.Counter(
        need(e, "klass", str, "abyss table entry") for e in abyss_entries
    )
    total = sum(c["count"] for c in summary.values())
    if total <= 0:
        raise FetchError("abyss class-summary: total ranked count is zero")
    rows = []
    for k, c in summary.items():
        m = metrics.get(k, {})
        rows.append(
            [
                ab_snapshot,
                k,
                NAMES[k],
                role(k),
                c["max_score"],
                c["top10_min_score"],
                blank(m.get("top10_avg_score")),
                blank(m.get("top100_cut_score")),
                c["avg_score"],
                c["count"],
                f"{100 * c['count'] / total:.2f}",
                abdist.get(k, 0),
            ]
        )
    rows.sort(key=lambda r: -r[5])
    out["mabimobi-abyss-class.csv"] = rows

    # Abyss daily trend.
    rows = []
    for c in ab_classes:
        k = c["klass"]
        trend = need(c, "trend", list, f"abyss daily classes klass {k}")
        if not known(k, bool(trend), "abyss daily classes"):
            continue
        for tr in trend:
            where = f"abyss trend klass {k}"
            rows.append(
                [
                    need(tr, "date", str, where),
                    k,
                    NAMES[k],
                    blank(tr.get("top1_score")),
                    blank(tr.get("top10_avg_score")),
                    blank(tr.get("top100_cut_score")),
                ]
            )
    rows.sort(key=lambda r: (r[0], r[1]))
    out["mabimobi-abyss-daily.csv"] = rows
    ab_dates = sorted({r[0] for r in rows})

    # Top-100 class distribution for both rankings.
    nm_entries = need(nm_table, "entries", list, "nightmare table")
    nmdist = collections.Counter(
        need(e, "klass", str, "nightmare table entry") for e in nm_entries
    )
    ab_table_snapshot = need(ab_table, "snapshot_date", str, "abyss table")
    rows = []
    for k in sorted(NAMES):
        if k not in summary:
            raise FetchError(
                f"abyss class-summary has no entry for klass {k} ({NAMES[k]})"
            )
        rows.append(
            [
                k,
                NAMES[k],
                role(k),
                nm_snapshot,
                dist.get(k, 0),
                nmdist.get(k, 0),
                ab_table_snapshot,
                abdist.get(k, 0),
                summary[k]["count"],
                f"{100 * summary[k]['count'] / total:.2f}",
            ]
        )
    out["mabimobi-top100-distribution.csv"] = rows

    info = {
        "requests": requests,
        "abyss_season_start": abyss_season_start,
        "nightmare_snapshot": nm_snapshot,
        "abyss_snapshot": ab_snapshot,
        "nightmare_dates": (nm_dates[0], nm_dates[-1], len(nm_dates)),
        "abyss_dates": (ab_dates[0], ab_dates[-1], len(ab_dates)) if ab_dates else None,
    }
    return out, info


# ---------------------------------------------------------------- output

HEADERS = {
    "mobiscore-dps-by-class.csv": [
        "category",
        "class",
        "n",
        "best",
        "top10_median",
        "median",
        "top10_median_seconds",
    ],
    "mabimobi-nightmare-class.csv": [
        "snapshot_date",
        "klass",
        "class",
        "role",
        "top1_zone",
        "top1_time",
        "top1_sec",
        "rank10_zone",
        "rank10_time",
        "rank10_sec",
        "rank100_cut_zone",
        "rank100_cut_time",
        "rank100_cut_sec",
        "top10_avg_zone",
        "ranked_in_class",
        "count_in_overall_top100",
    ],
    "mabimobi-nightmare-daily.csv": [
        "date",
        "klass",
        "class",
        "top10_avg_zone",
        "top1_zone",
        "top1_time",
        "top1_sec",
        "rank100_cut_zone",
        "rank100_cut_time",
        "rank100_cut_sec",
    ],
    "mabimobi-abyss-class.csv": [
        "snapshot_date",
        "klass",
        "class",
        "role",
        "top1_score",
        "top10_cut_score",
        "top10_avg_score",
        "top100_cut_score",
        "avg_score_all_ranked",
        "ranked_count",
        "ranked_share_pct",
        "count_in_overall_top100",
    ],
    "mabimobi-abyss-daily.csv": [
        "date",
        "klass",
        "class",
        "top1_score",
        "top10_avg_score",
        "top100_cut_score",
    ],
    "mabimobi-top100-distribution.csv": [
        "klass",
        "class",
        "role",
        "nightmare_snapshot",
        "nightmare_top100_count_api",
        "nightmare_top100_count_table",
        "abyss_snapshot",
        "abyss_top100_count",
        "abyss_ranked_count_all",
        "abyss_ranked_share_pct",
    ],
}


def validate(tables):
    """Each CSV must cover at least MIN_CLASSES distinct classes."""
    for name, rows in tables.items():
        col = HEADERS[name].index("class")
        n = len({r[col] for r in rows})
        if n < MIN_CLASSES:
            raise FetchError(
                f"{name} would cover only {n} classes (need {MIN_CLASSES})"
            )


def write_all(out_dir, tables):
    out_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for name, rows in tables.items():
            fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=out_dir)
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(HEADERS[name])
                w.writerows(rows)
            staged.append((tmp, out_dir / name))
        for tmp, dest in staged:
            os.replace(tmp, dest)
    finally:
        for tmp, _ in staged:
            if os.path.exists(tmp):
                os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    ap.add_argument(
        "--season-start",
        default="2026-09-17",
        help="mobi-score: keep records created on or after this date (YYYY-MM-DD)",
    )
    ap.add_argument(
        "--abyss-season-start",
        default=None,
        help="mabimobi.life Abyss season_start (e.g. 2026-09-16T21:00:00Z); "
        "default: discovered from /seasons",
    )
    ap.add_argument(
        "--nightmare-scope",
        default="current",
        help="mabimobi.life Nightmare Drill scope parameter (default: current)",
    )
    ap.add_argument(
        "--chrome", default="/opt/google/chrome/chrome", help="Chrome binary"
    )
    args = ap.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.season_start):
        ap.error("--season-start must be YYYY-MM-DD")

    try:
        log("== mobi-score.com")
        ms_rows, ms_info = fetch_mobiscore(args.season_start)
        log("== mabimobi.life")
        tables, mm_info = fetch_mabimobi(
            args.chrome, args.nightmare_scope, args.abyss_season_start
        )
        tables = {"mobiscore-dps-by-class.csv": ms_rows, **tables}
        if ms_info["classes"] < MIN_CLASSES:
            raise FetchError(
                f"mobi-score data covers only {ms_info['classes']} classes"
            )
        validate(tables)
        write_all(args.out, tables)
    except FetchError as e:
        log(f"ERROR: {e}")
        log("No files were written.")
        return 1

    print(f"Wrote {len(tables)} files to {args.out}")
    for name, rows in tables.items():
        print(f"  {name}: {len(rows)} rows")
    print(
        f"mobi-score: {ms_info['requests']} requests, records "
        f"{ms_info['date_range'][0]} .. {ms_info['date_range'][1]} "
        f"(season start {args.season_start})"
    )
    nd = mm_info["nightmare_dates"]
    print(
        f"mabimobi.life: {mm_info['requests']} requests; Nightmare Drill snapshot "
        f"{mm_info['nightmare_snapshot']}, daily {nd[0]} .. {nd[1]} ({nd[2]} days)"
    )
    ad = mm_info["abyss_dates"]
    print(
        f"  Abyss season_start {mm_info['abyss_season_start']}, snapshot "
        f"{mm_info['abyss_snapshot']}, daily {ad[0]} .. {ad[1]} ({ad[2]} days)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
