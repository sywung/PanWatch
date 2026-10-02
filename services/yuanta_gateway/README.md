# 元大 SparkAPI 唯讀行情轉接服務

此服務將元大 SparkAPI 的報價與 K 線查詢轉成簡單的 HTTP API，程式獨立於 PanWatch。服務只提供唯讀行情，不提供任何交易或資金操作功能。

## 建置

在 repo 根目錄執行：

```sh
docker build --platform linux/amd64 -t yuanta-gateway services/yuanta_gateway
```

映像不含元大 SDK。執行時將本機 SDK 目錄唯讀掛載，並以 env 檔與憑證檔提供設定：

```sh
docker run --rm --platform linux/amd64 \
  -p 127.0.0.1:2885:2885 \
  --env-file ~/.config/yuanta-gateway/yuanta.env \
  -v ~/Downloads/YuantaSparkAPI_linux-x64_Python:/sdk:ro \
  -v ~/.config/yuanta-gateway/cert.pfx:/config/cert.pfx:ro \
  yuanta-gateway
```

env 檔只需設定以下欄位：

```text
YUANTA_ACCOUNT
YUANTA_PASSWORD
YUANTA_PFX_PASSWORD
YUANTA_PFX_PATH
YUANTA_ENV
YUANTA_SDK_DIR
GATEWAY_TOKEN
```

`YUANTA_PFX_PATH` 預設為 `/config/cert.pfx`，`YUANTA_ENV` 預設為 `PROD`，`YUANTA_SDK_DIR` 預設為 `/sdk`。設定 `GATEWAY_TOKEN` 時，除健康檢查外的路由都需要 Bearer token。

## 健康檢查

```sh
curl http://127.0.0.1:2885/health
```

`/health` 不需要 token，回傳連線、登入狀態、遮罩帳號、最近錯誤與環境名稱。

## 已知限制

- 元大安控限制登入失敗後至少間隔 4 秒；一般查詢間隔至少三分之一秒，K 線查詢至少 1 秒。程式會自行遵守。
- `GetWatchListAll` 單次最多 600 檔。
- 在 QEMU 模擬下執行 .NET runtime 時必須關閉 W^X；映像已設定 `DOTNET_EnableWriteXorExecute=0`。
- SDK 與憑證由執行環境唯讀掛載，請勿放入 repo 或映像。
