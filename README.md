# 瑪奇手遊 韓服職業改版與強度

瑪奇手遊（마비노기 모바일）韓服 21 個職業的改版紀錄與 S2 職業強度。

- 改版紀錄：每個職業在每次改版的增強、削弱與修正，逐項附 Nexon 官方更新公告連結。查核範圍是 2025/04/03～2026/10/01 的 43 份官方更新說明（업데이트 노트），查核日 2026/10/13。
- S2 職業強度：依兩個粉絲網站在 2026/10/14 的資料，列出 Nightmare Drill 排行，以及依輸出、坦克、治癒分組的團戰 DPS 排行。

網頁：<https://mingdaygood-ops.github.io/mabinogi-class-timeline/>

## 檔案

| 檔案 | 用途 |
| --- | --- |
| `report.md` | 網頁內容（Markdown），要改文字或表格就改這份 |
| `template.html` | 網頁版面、樣式、分頁與搜尋 |
| `build.py` | 把 `report.md` 轉成 `docs/index.html`，並產生改版總覽矩陣 |
| `charts.py` | 從 `docs/data/s2-strength/` 的 CSV 產生 S2 職業強度頁的圖表 |
| `docs/index.html` | build 產出的網頁，GitHub Pages 發布這個檔案 |
| `docs/data/s2-strength/` | S2 職業強度的原始資料（CSV），網頁上也有下載連結 |
| `tools/check_report.py` | 檢查 `report.md` 的一致性：賽季標記、類型、公告連結、括號、殘留韓文、舊用語 |
| `tools/glossary.py` | 從現有內文抽出「中文（韓文）」譯名，`--lookup` 查詢、`--conflicts` 找出一詞多譯 |
| `tools/fetch_strength.py` | 從 mobi-score.com 與 mabimobi.life 重新抓 S2 職業強度的 CSV |
| `CLAUDE.md` | 給 Claude Code 的專案規則：命名格式、類型、用語、資料來源、發布方式 |
| `.claude/skills/update-timeline/` | `/update-timeline`：新增一次改版或更新強度資料的步驟 |
| `.claude/agents/` | `patch-translator`（把公告整理成表格列）、`content-reviewer`（唯讀審核） |

## 更新網頁

```bash
pip install markdown
python3 tools/check_report.py
python3 tools/glossary.py --conflicts
python3 build.py
git add report.md docs/
git commit -s -m "docs: update report"
git push
```

改了內容的話，記得同時更新 `report.md` 第 3 行的「最後更新：YYYY/MM/DD」（會顯示在網頁頁首），並在使用說明的「更新紀錄」加一筆。push 之後約一兩分鐘，GitHub Pages 會自動更新。

S2 職業強度的 CSV 是 2026/10/14 的快照，從 mobi-score.com（모비스코어）與 mabimobi.life（모비라이프）網頁使用的 API 取得。要更新強度資料，執行 `python3 tools/fetch_strength.py` 換掉 `docs/data/s2-strength/` 裡的 CSV，再重新 build；`report.md` 裡寫死的數字與結論要另外跟著改。

用 Claude Code 更新時，可以直接說「加入 10/15 的改版」或「更新強度資料」，或執行 `/update-timeline`，Claude 會照 skill 的步驟找公告、派 agent 翻譯與審核、檢查後 build。

## GitHub Pages 設定

repo 的 Settings → Pages，Source 選「Deploy from a branch」，Branch 選 `main`、資料夾選 `/docs`。

## 聲明

非官方整理，數值以遊戲內與官方公告為準。台服的改版日期與韓服不同，本資料只適用韓服。S2 職業強度的資料來自粉絲網站，網站自稱非官方資料，只適合當選職業的參考。
