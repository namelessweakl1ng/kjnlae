"""Bounded body collection and per-peer token bucket, independent of body assertions."""

import asyncio
import logging
import time
from collections import OrderedDict

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("kjnlae.audit")


class LimitsMiddleware:
    def __init__(self, app: ASGIApp, rate: int = 60, body_timeout: float = 10) -> None:
        self.app, self.rate = app, rate
        self.body_timeout = body_timeout
        self.peers: OrderedDict[str, tuple[float, float]] = OrderedDict()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        if scope.get("method") in {"POST", "PUT", "PATCH"}:
            try:
                async with asyncio.timeout(self.body_timeout):
                    while True:
                        event = await receive()
                        if event["type"] == "http.disconnect":
                            return
                        body.extend(event.get("body", b""))
                        if len(body) > 131072:
                            await JSONResponse({"error": "request_too_large"}, status_code=413)(
                                scope, receive, send
                            )
                            return
                        if not event.get("more_body"):
                            break
            except TimeoutError:
                log.info("http_result", extra={"status": 408, "method": scope["method"]})
                await JSONResponse({"error": "request_timeout"}, status_code=408)(
                    scope, receive, send
                )
                return
        if scope.get("path", "").startswith("/v2/"):
            peer = str((scope.get("client") or ("unknown", 0))[0])
            now = time.monotonic()
            tokens, previous = self.peers.pop(peer, (float(self.rate), now))
            tokens = min(self.rate, tokens + (now - previous) * self.rate / 60)
            if len(self.peers) >= 1024:
                self.peers.popitem(last=False)
            self.peers[peer] = (max(0, tokens - 1), now)
            if tokens < 1:
                await JSONResponse(
                    {"error": "rate_limit"}, status_code=429, headers={"Retry-After": "60"}
                )(scope, receive, send)
                return
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def audited_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Do not log paths or query strings (may contain sensitive client data).
                log.info(
                    "http_result", extra={"status": message["status"], "method": scope["method"]}
                )
                csp = (
                    b"default-src 'self'; script-src 'self'; style-src 'self'; "
                    b"connect-src 'self'; img-src 'self' data:; "
                    b"frame-ancestors 'none'; base-uri 'self'"
                )
                if scope.get("path") in {"/docs", "/redoc"}:
                    # Only static developer documentation needs trusted CDN/inline bundles.
                    # These routes are absent in production. Dashboard CSP stays strict.
                    csp = (
                        b"default-src 'self'; "
                        b"script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                        b"style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                        b"connect-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
                        b"frame-ancestors 'none'; base-uri 'self'"
                    )
                message["headers"].extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"cache-control", b"no-store"),
                        (
                            b"content-security-policy",
                            csp,
                        ),
                    ]
                )
            await send(message)

        await self.app(scope, bounded_receive, audited_send)
