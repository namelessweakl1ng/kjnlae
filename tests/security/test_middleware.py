import asyncio

from kjnlae.api.middleware import LimitsMiddleware


def test_slow_request_body_has_a_deadline():
    async def run():
        sent = []
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        async def receive():
            await asyncio.sleep(1)
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        middleware = LimitsMiddleware(app, body_timeout=0.01)
        await middleware({"type": "http", "method": "POST", "path": "/v2/scan"}, receive, send)
        assert not called and sent[0]["status"] == 408

    asyncio.run(run())


def test_chat_route_is_rate_limited():
    async def run():
        statuses = []

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                statuses.append(message["status"])

        middleware = LimitsMiddleware(app, rate=1)
        scope = {"type": "http", "method": "POST", "path": "/chat", "client": ("local", 1)}
        await middleware(scope, receive, send)
        await middleware(scope, receive, send)
        assert statuses == [200, 429]

    asyncio.run(run())


def test_oversized_request_still_rejected():
    """Allow valid encoded Unicode scans, but keep an explicit byte ceiling."""
    async def run():
        statuses = []
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        async def receive():
            return {"type": "http.request", "body": b"x" * (512 * 1024 + 1), "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                statuses.append(message["status"])

        middleware = LimitsMiddleware(app)
        scope = {"type": "http", "method": "POST", "path": "/v2/scan"}
        await middleware(scope, receive, send)
        assert not called and statuses == [413]

    asyncio.run(run())
