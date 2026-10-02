# 元大 SparkAPI 行情轉接服務（唯讀）

把元大證券 SparkAPI 的即時報價與 K 線，轉成一個本機 HTTP 服務，讓 PanWatch（或其他程式）可以當資料來源使用。

- **只讀行情**：程式裡沒有任何下單、委託、條件單、圈存、預繳功能。
- **帳密與憑證只在你的電腦上**：以唯讀方式掛進容器，不寫進映像、不寫進 log、不傳給 PanWatch。
- **元大 SDK 不隨本專案散布**：請自行向元大下載。

## 前置條件

1. 元大證券帳戶已**線上簽署 API** 並請營業員**開通**行情 API。
2. 有元大的**憑證檔（`.pfx`）**與憑證密碼。
3. 從元大下載 **SparkAPI Linux x64 Python 版**，解壓到一個資料夾（例如 `~/yuanta-sdk`）。
4. 已安裝 Docker（或 Podman）。

> Apple Silicon（M 系列）Mac 一樣用 Linux x64 版，Docker 會用模擬執行；映像已預先設定好避免 .NET 在模擬下卡住的參數。

## 安裝

### 1. 準備設定檔（只有你看得到）

```sh
mkdir -p ~/.config/yuanta-gateway && chmod 700 ~/.config/yuanta-gateway
cp 你的憑證.pfx ~/.config/yuanta-gateway/cert.pfx
chmod 600 ~/.config/yuanta-gateway/cert.pfx
```

建立 `~/.config/yuanta-gateway/yuanta.env`（`chmod 600`），內容欄位：

| 欄位 | 說明 |
|---|---|
| `YUANTA_ACCOUNT` | 證券帳號：`S` + 分公司代號 4 碼 + 帳號 7 碼 |
| `YUANTA_PASSWORD` | 登入密碼 |
| `YUANTA_PFX_PASSWORD` | 憑證密碼 |
| `GATEWAY_TOKEN` | （選用）設定後，除 `/health` 外都要帶 `Authorization: Bearer <token>` |
| `YUANTA_ENV` | （選用）`PROD`（預設）或 `UAT` 測試環境 |
| `GATEWAY_PORT` | （選用）服務 port，預設 `2885` |

### 2. 建置映像

在 PanWatch repo 根目錄：

```sh
docker build --platform linux/amd64 -t yuanta-gateway services/yuanta_gateway
```

### 3. 執行

```sh
docker run -d --name yuanta-gateway --restart unless-stopped --platform linux/amd64 \
  -p 127.0.0.1:2885:2885 \
  --env-file ~/.config/yuanta-gateway/yuanta.env \
  -v ~/.config/yuanta-gateway/cert.pfx:/config/cert.pfx:ro \
  -v ~/yuanta-sdk:/sdk:ro \
  yuanta-gateway
```

`-p 127.0.0.1:2885:2885` 只讓本機連得到；不要改成 `0.0.0.0`。

### 4. 確認

```sh
curl http://127.0.0.1:2885/health
```

`"logged_in": true` 就是登入成功。

## `/health` 欄位

| 欄位 | 說明 |
|---|---|
| `connected` / `logged_in` | 是否已連線／登入 |
| `account` | 遮罩後的帳號 |
| `last_error` | 最近錯誤（見下表） |
| `retry_allowed` | `false` 表示已停止自動登入，需要修正設定後**重啟容器** |

| `last_error` | 原因與處理 |
|---|---|
| `missing_credentials` | env 檔少了帳號、密碼或憑證密碼 |
| `missing_certificate` | 找不到 `/config/cert.pfx`，檢查掛載路徑 |
| `0102 ...` 等登入代碼 | 帳密錯誤、密碼凍結或未啟用 → 修正後重啟 |
| `certificate error` | 憑證錯誤或過期 |
| `suspended` | 元大停權 → 聯絡營業員 |
| `rate_limited` | 觸發元大使用次數限制 |
| `Login timeout` / `disconnected` / `network_error` | 網路問題，服務每 60 秒自動重試 |

## 登入保護

元大有**每日登入次數**、**黑名單**與**停權**機制。為了不讓錯誤設定把帳號鎖住：

- 缺設定、帳密錯誤、憑證錯誤、停權時，**不會自動重試**，只會在 `/health` 顯示原因。
- 只有逾時、斷線這類網路問題才自動重試（每 60 秒，且兩次登入間隔至少 4 秒）。

## API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/health` | 狀態（免 token） |
| POST | `/quotes` | body：`{"items":[{"market":"TSE","code":"2330"}]}`，一次最多 600 檔 |
| GET | `/kline` | `?market=TSE&code=2330&period=1d&start=2026-09-01&end=2026-10-02` |

- `market`：`TSE` 上市、`OTC` 上櫃、`ESB` 興櫃、`TAIFEX` 期貨。
- `period`：`1m` `5m` `15m` `30m` `60m` `1d` `1w` `1M`。
- 錯誤碼：400 參數錯誤、401 token 錯誤、503 尚未登入、504 元大逾時。

## 已知限制

- 元大安控：同功能查詢每秒最多 3 次、K 線每秒 1 次、訂閱總數 2000 檔；服務會自動排隊遵守。
- Docker 主機休眠或關機時服務中斷，PanWatch 會改用其他資料來源。
- 有說法指出行情 API 長期未下單可能被停權，請向營業員確認。
