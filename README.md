# 中部產業情報中心 / Central Taiwan Industry Intelligence

GitHub Pages website for public news indexing covering 機械、自行車、汽配、手工具.

## 第一版目前功能

- 16 組台灣／北美／歐洲／日本的 Google News RSS 搜尋，每日由 GitHub Actions 執行
- 保存文章標題、媒體、發布日期、原文網址及產業標籤，不擷取文章全文
- 首頁提供全文關鍵字、產業、地區與情報主題篩選
- 不使用付費 API，公開頁面請勿存入任何私人或內部業務資料

## 尚未完成

- 外文新聞自動翻譯與繁體中文摘要
- AI 每日因果分析
- 專業媒體直接 RSS/API 蒐集及驗證
- 官方統計數據自動連接

目前只是新聞索引第一版，不可將原文標題冒充已完成中文翻譯或 AI 分析。

## 網站發布

1. 進入 GitHub 儲存庫 Settings → Pages
2. Build and deployment 選擇 Deploy from a branch
3. Branch 選擇 main，資料夾選 /(root)，按 Save
4. 到 Actions → Daily industry news → Run workflow 手動進行首次資料更新
5. 在 Actions 頁面檢查執行結果與 data/news.json

每日排程時間為 UTC 00:23（台灣 08:23），GitHub 排程可能延遲或漏執行，應檢查執行狀態。新聞內容著作權屬原始發布者，資料以來源網站為準。

## 資料來源

- config/queries.json：各產業與地區新聞搜尋條件
- config/sources.json：候選專業媒體與官方來源（**尚未驗證直接可自動擷取**）
- scripts/collect.py：RSS 新聞索引蒐集程式

## 2026-11-19 新增功能

- 第五個分類「無人載具及機器人」，含台灣、美國、歐洲、日本共 4 組搜尋。
- 每天台灣時間 09:00 排程執行一次（GitHub Actions 實際啟動可能延遲）。
- `data/news.json` 不再只保留 1,200 筆；新增 `data/archive/YYYY-MM-DD.json` 每日新聞蒐集快照，隨 Actions 提交 GitHub。資料持續累積時仍須留意檔案及 GitHub Pages 使用限制。
- 新聞列表點擊後先前往 `article.html?id=...`，依序顯示中文摘要區、原文標題與原始來源連結。
- **目前尚未實作 AI 摘要產生器**：因現有 RSS 僅有標題資訊，不能捏造摘要；未取得足夠原文時，頁面會清楚標示「尚未完成」。
- 寄送每日郵件**尚未啟用**：需確認指定收件信箱、授權寄信方式及寄信服務是否符合零額外費用限制。信件未來可提供站內文章網址，讓收件者閱讀已有的繁體中文摘要。
- 原文不直接全文複製到本站，除非來源授權或有其他合法取得條件。

## 2026-11-19 新設計與實作狀態

- 網站配色改為低飽和暖橘、米白、棕色（已提交，待 Pages 部署同步）。
- 公開新聞索引保留最近 **30 天**；每日快照保留 30 天，超過時由蒐集程式移除工作樹中的舊快照。**Git 歷史版本不會因此消失**，長期使用仍應檢視儲存庫大小。
- 首頁顯示繁中標題優先，下面最多顯示兩行有根據的中文摘要；沒有足夠原始資料就明示摘要未完成。
- 免費 Argos Translate 離線翻譯納入 Actions：有語言模型可用時翻譯英／日文標題，並可翻譯真正有意義的 RSS 來源摘要；尚未經實際 Actions 測試，且機器譯文不等於 GPT／Claude AI 摘要。不得由標題捏造摘要。
- Google News RSS 的結果**不保證全部免登入或免付費全文可讀**；目前排除部分已知付費／報告導購來源，但這只是初步篩選。正式要達成「所有文章免費可讀」，必須改為逐一確認免登入的來源白名單與直接文章連結，並實際測試。資料上的 access_status 為 not_verified。
- Gmail 電子報範本已調整成五大產業各最多五則精選、去重、橘色版型；**使用者自己 Google Apps Script 專案中的舊程式不會自動同步**，須重新貼上 integrations/google-apps-script/daily_digest.gs 才會使用新範本。
- 郵件寄件者取決於建立 Apps Script 排程並授權的 Google 帳號，不是 GitHub 的寄件身分。需要確認使用 taitra.eva@gmail.com 執行授權。
- 零付費 API：尚未實現每天無人值守的 GPT／Claude 長篇 AI 摘要；只有可靠原文與可用的模型／合法資料來源時才可產生。
