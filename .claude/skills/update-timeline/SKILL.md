---
name: update-timeline
description: Update the Mabinogi Mobile KR class site - add a new official update note (patch) to report.md, or refresh the S2 class-strength data from the fan sites - then check, build and publish. Use when the user says things like "加入 10/15 的改版", "更新強度資料", "有新的更新說明", "update the timeline", or asks to refresh the site.
---

# update-timeline

Two workflows. Read the repo CLAUDE.md first; its content rules apply to every step. Talk to the user in
zh-TW. Ask before publishing unless the user already asked to publish.

## A. Add a new patch

1. Find what is new. The last covered date is the first row of the 來源清單 table in report.md.
   Patches go live on Thursday maintenance. For each new date you need the notice text and the official
   notice id (`https://mabinogimobile.nexon.com/News/Update/<id>`).
   - The official site is geo-blocked here. Look for a repost on the Inven free board: scan post numbers
     after the last known one (`https://www.inven.co.kr/board/mabimo/6259/<n>`, curl with a desktop
     User-Agent, read the title and articleDate) for titles like `M/D(목) 업데이트 노트`.
   - WebSearch for `마비노기 모바일 M/D 업데이트 노트` may return the official URL and its id.
   - If the id or text cannot be found, ask the user for the official link before going on.
2. Read the notice and list which classes changed, plus shared changes (全職業共通變動). A notice with no
   class changes still gets a 來源清單 row marked 無職業改動.
3. Dispatch `patch-translator` agents in parallel, one per class group with changes (戰士系, 弓箭手系,
   魔法師系, 治癒師系, 吟遊詩人系, 盜賊系, and one for 全職業共通變動 if needed). Give each: live date,
   notice id, notice text or repost URL, its classes, and an output path in the scratchpad
   (`<scratchpad>/patch-YYYYMMDD/<group>.json`).
4. Apply all edit lists in one script: load every JSON, assert each `old` occurs exactly once in the
   current text before replacing, and write report.md only after all assertions pass.
5. Update by hand:
   - 來源清單 table: new row at the top (date, linked notice, classes affected).
   - `最後更新：YYYY/MM/DD` on report.md line 3, and a new line in 使用說明 › 更新紀錄.
   - 使用說明 and README if the covered range (`2025/04/03～YYYY/MM/DD`, notice count) changed; the page
     header line in template.html shows the change-log check date and notice count too.
6. Check: `python3 tools/check_report.py`, `python3 tools/glossary.py --conflicts`, and the doc-review
   checker on report.md. Fix every failure.
7. Review: dispatch `content-reviewer` on the class sections that changed. Apply its edits the same way as
   step 4; relay its "unverifiable" list to the user.
8. Build and look: `python3 build.py`, serve `docs/` locally and screenshot the overview matrix and one
   changed class tab (desktop and 390 px mobile).
9. Publish (when asked): stage files explicitly, commit with
   `env -u GIT_AUTHOR_NAME -u GIT_AUTHOR_EMAIL git commit -s`, push, then poll the live site until it is
   byte-identical to `docs/index.html`.

## B. Refresh the S2 strength data

1. `python3 tools/fetch_strength.py --out <scratchpad>/strength-new` (add `--season-start` when the ranking
   period changed). Compare with `docs/data/s2-strength/`: same headers, 21 classes, sensible dates.
   The tool follows the sites' current ranking period; decide with the user whether the page should move
   to the new period, and change the S2 section's period dates and wording if it does.
2. Copy the new CSVs into `docs/data/s2-strength/`.
3. Re-derive every number written in the S2 職業強度 prose (結論 bullets, 這一期的變化, 跟社群評價對照,
   資料來源與方法 sample sizes and dates, the intro snapshot date) from the CSVs with a script; never copy
   numbers from memory. Update the snapshot date in report.md, template.html header/footer and README.
4. Steps A6～A9 (checks, review of the S2 section, build and screenshots, publish when asked).

## Division of work

- Main conversation: finds sources, dispatches agents, applies edits, runs checks, builds, publishes.
- `patch-translator`: turns notice text into rows and bullet edits for its classes; returns JSON only.
- `content-reviewer`: read-only; checks prose against tables, sources and rules; returns JSON only.
- `tools/`: deterministic work (fetching strength data, consistency checks, glossary lookups).
- Community research for 社群評論 is optional and ad hoc; use a general-purpose agent with the rules in
  CLAUDE.md when the user asks for it.
