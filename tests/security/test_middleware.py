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
        await middleware({"type": "http", "method": "POST", "path": "/v1/scan"}, receive, send)
        assert not called and sent[0]["status"] == 408

    asyncio.run(run())
