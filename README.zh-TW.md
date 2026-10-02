# 盯盤俠 PanWatch（台股版）— 自架 AI 盯盤助手

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文（台股版）](README.zh-TW.md)

**把自選股與持倉變成全天候的 AI 投研工作台。** 本分支以台灣股市為主：預設市場是台股、以新台幣計價、介面預設繁體中文，並接上證交所、櫃買中心、集保等台灣資料來源。原有的 A 股、港股、美股功能都保留。

本專案 fork 自 [TNT-Likely/PanWatch](https://github.com/TNT-Likely/PanWatch)（MIT 授權）。AI 深度分析整合 [TradingAgents](https://github.com/TauricResearch/TradingAgents) 多 Agent 投資決策框架。

[和上游的差異](#和上游的差異) · [快速開始](#快速開始) · [首次設定](#首次設定) · [台股資料來源](#台股資料來源) · [已知限制](#已知限制) · [本地開發](#本地開發) · [與上游同步](#與上游同步)

## 和上游的差異

| 項目 | 上游 PanWatch | 本分支 |
| :--- | :--- | :--- |
| 支援市場 | A 股／港股／美股 | **台股（上市、上櫃、興櫃、ETF）**＋A 股／港股／美股 |
| 預設市場 | A 股 | **台股**（台股不顯示市場標籤，其他市場加標籤） |
| 計價幣別 | 人民幣 | **新台幣**（匯率來自 Yahoo，外幣持倉自動換算） |
| 介面語言 | 簡中／英文 | **繁體中文（預設）**／簡中／英文 |
| 時區 | Asia/Shanghai | **Asia/Taipei** |
| Agent 預設排程 | A 股交易時段 | **台股交易時段**（見下表） |
| 大盤指數 | 上證／深證／創業板／恆生／那斯達克 | 先顯示**加權指數、櫃買指數** |
| 組合比較基準 | 滬深 300 | **加權指數** |

### 台股功能

- **即時報價**：證交所 mis（上市＋上櫃）→ Fugle（興櫃，需 API key）→ 櫃買興櫃盤後行情 → Yahoo，缺的代碼才往下一個來源補
- **K 線**：Yahoo（上市 `.TW`／上櫃與興櫃 `.TWO`，自動判斷並記住）
- **交易日曆**：證交所休市日（含補假、「最後交易日／開始交易日」判斷）
- **股票搜尋**：上市、上櫃、興櫃全清單，簡體或繁體名稱都搜得到，興櫃會標示
- **AI 分析**：收盤複盤、盤前分析、盤中監測都會帶入三大法人、融資融券等台股資料，提示詞會說明台股規則（漲跌幅 ±10%、可當沖、單位「張」）
- **模擬盤**：台股手續費 0.1425%、證交稅 0.3%（ETF 0.1%），可零股
- **機會發現**：台股熱門股（依成交金額或漲幅，盤後資料）

## 快速開始

本分支目前沒有發布現成的 Docker image，請從原始碼建置：

```bash
git clone https://github.com/sywung/PanWatch.git
cd PanWatch
git checkout feat/tw-market

docker build -t panwatch-tw .        # 使用 Podman 時把 docker 換成 podman
docker run -d \
  --name panwatch-tw \
  --restart unless-stopped \
  -p 8000:8000 \
  -v panwatch_tw_data:/app/data \
  panwatch-tw
```

開啟 `http://localhost:8000`，第一次進入會請你設定帳號密碼。

- image 內已包含 Playwright 所需的系統套件；Chromium 會在容器第一次啟動時下載到掛載的 volume，需要幾分鐘且要能連網。不需要 K 線截圖功能的話，啟動時加 `-e PLAYWRIGHT_SKIP_BROWSER_INSTALL=1` 跳過。
- 資料（帳號、持倉、設定、API key）都存在 volume 的 `/app/data`，換 image 不會遺失。

<details>
<summary>Docker Compose</summary>

```yaml
services:
  panwatch:
    build: .
    image: panwatch-tw
    container_name: panwatch-tw
    ports:
      - "8000:8000"
    volumes:
      - panwatch_tw_data:/app/data
    restart: unless-stopped

volumes:
  panwatch_tw_data:
```

```bash
docker compose up -d --build
```

</details>

<details>
<summary>環境變數</summary>

| 變數 | 說明 | 預設值 |
| :--- | :--- | :--- |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | 預設登入帳密（只在資料庫還沒有帳號時生效，不會覆蓋已設定的帳號） | 第一次進入時設定 |
| `JWT_SECRET` | JWT 簽章密鑰 | 自動產生 |
| `DATA_DIR` | 資料目錄 | `./data` |
| `TZ` | 時區，影響 Agent 排程觸發時間與畫面上的時間 | `Asia/Taipei` |
| `PLAYWRIGHT_SKIP_BROWSER_INSTALL` | 跳過第一次啟動時安裝 Chromium | 未設定 |
| `LOG_LEVEL` | 主控台日誌等級，除錯時可設 `DEBUG` | `INFO` |
| `PROMPT_LANGUAGE` | AI 提示詞（`prompts/*.txt`）語言：`auto` 跟著介面語言（繁中時轉繁體）、`zh-TW` 一律轉繁體、`original` 維持原檔 | `auto` |
| `HTTP_PROXY` / `HTTPS_PROXY` | 對外 HTTP 代理（也可在「設定 → 全域 HTTP 代理」設定） | 未設定 |

</details>

## 首次設定

1. 開啟網頁，設定登入帳號。
2. **設定 → AI 服務商**：設定 OpenAI 相容 API（OpenAI、Azure OpenAI、DeepSeek、Ollama 等）。推理型模型不接受自訂 temperature，系統會自動改用預設值重試，日誌出現一次 `Unsupported value: 'temperature'` 屬正常。
3. **設定 → 通知渠道**：加入 Telegram、企業微信、釘釘、飛書、Bark 或自訂 Webhook。
4. **持倉 → 新增股票**：輸入代號或名稱搜尋（例如「2330」或「台積電」）。
5. **Agent 頁**：Agent 預設只有「收盤複盤」是啟用的。要用的 Agent 請按「**啟用**」，並在持倉頁替個股**勾選要綁定的 Agent**——沒有綁定股票的 Agent 不會分析任何東西。
6. （選用）**資料源頁 → Fugle 行情（興櫃）**：貼上 [Fugle 富果](https://developer.fugle.tw/) 的 API key，興櫃股才會有即時報價；沒填會自動改用櫃買中心的盤後行情。

> 🔐 API key 存在 PanWatch 的資料庫（volume 內），不在程式碼或 repo 裡。`data/` 與 `.env` 都已列入 `.gitignore`。

### Agent 預設排程（台股時間）

| Agent | 預設排程 | 說明 |
| :--- | :--- | :--- |
| 盤前分析 | 週一至週五 08:30 | 綜合隔夜美股、新聞、技術面，給今日策略 |
| 盤中監測 | 週一至週五 09:00–13:55 每 5 分鐘 | 監控異動訊號並推播提醒 |
| 收盤複盤 | 週一至週五 14:00 | 回顧當日走勢、三大法人動向，規劃次日 |

排程可在 Agent 頁修改。台股的交易時段與休市日（國定假日、補假）依證交所日曆判斷；颱風等臨時停市不在日曆內。

> ⚠️ 預設排程只套用在新安裝；從舊版升級的資料庫會保留原本的排程，請到 Agent 頁自行調整。

## 台股資料來源

全部免費、免 key，Fugle 除外。

| 資料類型 | 來源 |
| :--- | :--- |
| 即時報價（上市／上櫃） | 證交所 mis `getStockInfo.jsp` |
| 即時報價（興櫃） | Fugle 富果 API（需 key）；備援：櫃買 `tpex_esb_latest_statistics`（盤後） |
| 報價備援 | Yahoo Finance |
| K 線、加權指數 | Yahoo chart API（`^TWII`、`.TW`、`.TWO`） |
| 加權／櫃買指數即時 | 證交所 mis（`t00`、`o00`） |
| 匯率（TWD） | Yahoo（`USDTWD=X`、`HKDTWD=X`、`CNYTWD=X`） |
| 休市日曆 | 證交所 openapi `holidaySchedule` |
| 股票清單 | 證交所 `STOCK_DAY_ALL`、櫃買 `tpex_mainboard_daily_close_quotes`、櫃買 `mopsfin_t187ap03_R`（興櫃） |
| 本益比／殖利率／股價淨值比 | 證交所 `BWIBBU_ALL`、櫃買 `tpex_mainboard_peratio_analysis` |
| 三大法人買賣超 | 證交所 `T86`、櫃買 `tpex_3insti_daily_trading` |
| 融資融券（單位：張） | 證交所 `MI_MARGN`、櫃買 `tpex_mainboard_margin_balance` |
| 股利／除權息 | 證交所 `t187ap45_L`、`TWT48U_ALL` |
| 重大訊息 | 證交所 `t187ap04_L`、櫃買 `mopsfin_t187ap04_O` |
| 注意股／處置股 | 證交所 `announcement/notice`、`announcement/punish` |
| 股權分散（大戶持股比例） | 集保 `getOD.ashx?id=1-5` |
| 個股新聞 | Yahoo 奇摩股市 RSS |
| 台股快訊 | 鉅亨網 |

各資料源可在「資料源」頁個別啟用、調整優先順序，並用「測試」按鈕確認連線。

## 已知限制

- **櫃買指數**：Yahoo 沒有對應代碼，只有即時報價，不能當組合比較基準，首頁也沒有走勢線。
- **熱門股票**：台股的熱門股是盤後資料（每日收盤後更新），不是盤中即時；台股沒有板塊榜。
- **TradingAgents 深度分析**：台股只支援 4 碼的上市股代號，上櫃、興櫃與 `00679B` 這類代碼尚未支援。
- **全市場搜尋**：會同時查詢東方財富的即時搜尋，從台灣連線可能等約 5 秒逾時；只選「台股」時不會查詢它。
- **開盤前（08:30–09:00）**：證交所 mis 沒有成交價，顯示的是委買第一檔（試撮價）。
- **台指期**：尚未支援。

## 本地開發

**環境需求**：Python 3.11、Node.js 24.14.0、pnpm 9.15.9

```bash
make dev-api          # 後端 :8000（自動建立 venv 並安裝依賴）
make dev-web          # 前端 :5183（/api 代理到 127.0.0.1:8000）
```

<details>
<summary>測試</summary>

```bash
python -m pytest tests packages/marketdata/tests -q    # 後端
cd frontend && pnpm exec vitest run                     # 前端
cd frontend && pnpm exec tsc -b                         # 型別檢查
node frontend/scripts/check-i18n-literals.mjs           # 檢查元件內是否寫死文字
```

- 前端測試請用 Node 24。Node 25 以上內建的 `localStorage` 與 jsdom 衝突，測試會在 setup 階段全部失敗。
- 只動到台股資料源的話，可以先跑 `tests/test_tw_*.py` 與 `packages/marketdata/tests/test_tw_*.py`；測試都用 `packages/marketdata/tests/fixtures/tw/` 裡的真實回應樣本，不會連網。

</details>

<details>
<summary>繁體中文語系檔</summary>

`frontend/src/i18n/locales/zh-TW/` 是由簡體中文語系**自動產生**的，不要直接修改：

```bash
python frontend/scripts/gen-zh-tw.py
```

腳本用 OpenCC `s2twp` 轉換為台灣用語，再套用固定的修正（例如「臺」→「台」、「賬」→「帳」、引號改「」）。需要逐條修正時，寫進腳本裡的 `OVERRIDES`。新增介面文字時請同時更新 `zh-CN` 與 `en-US`，再重新執行腳本。

後端產生的文字（通知、AI 報告標題等）在介面語言為繁中時，會在送出前以同一套規則轉換（`src/platform/language.py` 的 `localize_text`）。

</details>

## 與上游同步

```bash
git remote add upstream https://github.com/TNT-Likely/PanWatch.git   # 只需設定一次
git fetch upstream
git merge upstream/main
python frontend/scripts/gen-zh-tw.py      # 上游新增了簡中文字時，重新產生繁中語系
```

本分支盡量把台股相關的預設值集中在常數（`DEFAULT_MARKET`、`ALL_MARKETS`、`BASE_CURRENCY`，位於 `src/platform/marketdata/models.py`），以減少合併時的衝突。`tests/test_default_market_sweep.py` 會掃描整個專案，若合併後出現新的寫死 A 股預設值，測試會失敗。

## 授權與致謝

[MIT](LICENSE)。原始專案由 [TNT-Likely/PanWatch](https://github.com/TNT-Likely/PanWatch) 開發，若這個專案對你有幫助，歡迎到上游給 ⭐ 或[支持原作者](https://github.com/TNT-Likely/PanWatch#support-the-project)。
