# 瑪奇手遊 韓服職業 Buff／Nerf 時間軸

瑪奇手遊（마비노기 모바일）韓服 20 個職業在每次改版的增強、削弱、重做與修正，按職業整理，每一項都附 Nexon 官方更新公告連結。資料查核範圍為 2025/04/03～2026/10/01 的 43 份官方「업데이트 노트」，查核日 2026/10/13。

- 網頁版：`docs/index.html`（透過 GitHub Pages 發布）
- 原始內容：`report.md`

## 檔案

| 檔案 | 用途 |
| --- | --- |
| `report.md` | 報告內容（Markdown），要改資料就改這份 |
| `template.html` | 網頁版面、樣式與篩選功能 |
| `build.py` | 把 `report.md` 轉成 `docs/index.html` |
| `docs/` | GitHub Pages 發布的資料夾 |

## 更新網頁

```bash
pip install markdown
python3 build.py
git add -A && git commit -m "Update report" && git push
```

## 開啟 GitHub Pages

到 repo 的 **Settings → Pages**，Source 選 **Deploy from a branch**，Branch 選 `main`、資料夾選 `/docs`，儲存後約一分鐘即可在 `https://<帳號>.github.io/<repo>/` 看到網頁。

## 聲明

非官方整理，數值以遊戲內與官方公告為準。台服改版日期與韓服不同，本資料只適用韓服。
