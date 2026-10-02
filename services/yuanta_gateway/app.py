"""唯讀行情 HTTP 服務。"""

from __future__ import annotations

import hmac
import os
import threading
from datetime import date

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from client import NotLoggedIn


class QuoteItem(BaseModel):
    market: str
    code: str


class QuotesRequest(BaseModel):
    items: list[QuoteItem]


def create_app(client) -> FastAPI:
    app = FastAPI(title="Yuanta Read-only Market Gateway")

    @app.middleware("http")
    async def bearer_auth(request, call_next):
        token = os.environ.get("GATEWAY_TOKEN", "")
        if request.url.path != "/health" and token:
            authorization = request.headers.get("Authorization", "")
            supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not supplied or not hmac.compare_digest(supplied, token):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    @app.exception_handler(NotLoggedIn)
    async def not_logged_in_handler(request, exc):
        return JSONResponse(status_code=503, content={"detail": str(exc) or "Not logged in"})

    @app.exception_handler(ValueError)
    async def value_error_handler(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(TimeoutError)
    async def timeout_handler(request, exc):
        return JSONResponse(status_code=504, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        return client.status()

    @app.post("/quotes")
    def quotes(body: QuotesRequest):
        items = [(item.market, item.code) for item in body.items]
        return {"data": client.quotes(items)}

    @app.get("/kline")
    def kline(market: str, code: str, period: str, start: date, end: date):
        return {"data": client.kline(market, code, period, start, end)}

    app.state.client = client
    return app


DEFAULT_PORT = 2885


def gateway_port() -> int:
    return int(os.environ.get("GATEWAY_PORT", DEFAULT_PORT))


def main():
    import uvicorn

    from dotnet_adapter import load_runtime
    from client import YuantaClient

    adapter = load_runtime(os.environ.get("YUANTA_SDK_DIR", "/sdk"))
    client = YuantaClient(
        adapter,
        account=os.environ.get("YUANTA_ACCOUNT", ""),
        password=os.environ.get("YUANTA_PASSWORD", ""),
        pfx_path=os.environ.get("YUANTA_PFX_PATH", "/config/cert.pfx"),
        pfx_password=os.environ.get("YUANTA_PFX_PASSWORD", ""),
        env=os.environ.get("YUANTA_ENV", "PROD"),
        log_dir="/var/log/yuanta-gateway",
    )
    if not os.path.isfile(os.environ.get("YUANTA_PFX_PATH", "/config/cert.pfx")):
        client.disable_login("missing_certificate")
    try:
        client.connect_and_login()
    except Exception as exc:
        # 不記錄 SDK 例外內容，避免把敏感設定帶入日誌。
        import logging

        logging.getLogger("yuanta_gateway").error("啟動登入失敗 (%s)", type(exc).__name__)

    app = create_app(client)
    stop_retry = threading.Event()
    app.state.retry_stop = stop_retry

    def retry_login():
        while not stop_retry.wait(60):
            status = client.status()
            if not status["logged_in"] and status.get("retry_allowed", False):
                try:
                    client.connect_and_login()
                except Exception as exc:
                    import logging

                    logging.getLogger("yuanta_gateway").error("重新登入失敗 (%s)", type(exc).__name__)

    retry_thread = threading.Thread(target=retry_login, name="yuanta-login-retry", daemon=True)
    retry_thread.start()

    @app.on_event("shutdown")
    def shutdown():
        stop_retry.set()
        client.close()

    uvicorn.run(app, host="0.0.0.0", port=gateway_port())


if __name__ == "__main__":
    main()
