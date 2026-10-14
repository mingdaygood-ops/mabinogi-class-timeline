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

## 更新網頁

```bash
pip install markdown
python3 build.py
git add report.md docs/
git commit -s -m "docs: update report"
git push
```

push 之後約一兩分鐘，GitHub Pages 會自動更新。

S2 職業強度的 CSV 是 2026/10/14 的快照，從 모비스코어（mobi-score.com）與 모비라이프（mabimobi.life）網頁使用的 API 取得，收集腳本不在這個 repo 裡。要更新強度資料，換掉 `docs/data/s2-strength/` 裡的 CSV（欄位維持不變），再重新 build；`report.md` 裡寫死的數字與結論要另外跟著改。

## GitHub Pages 設定

repo 的 Settings → Pages，Source 選「Deploy from a branch」，Branch 選 `main`、資料夾選 `/docs`。

## 聲明

非官方整理，數值以遊戲內與官方公告為準。台服的改版日期與韓服不同，本資料只適用韓服。S2 職業強度的資料來自粉絲網站，網站自稱非官方資料，只適合當選職業的參考。
