from fastapi import FastAPI

from app.api.routers.health import healthRouter
from app.api.routers.slack import slackRouter

app = FastAPI()
app.include_router(slackRouter)
app.include_router(healthRouter)

from fastapi import Request
from fastapi.responses import Response


@app.middleware("http")
async def debugSlack(request: Request, call_next):
    response = await call_next(request)

    if request.url.path != "/slack/events" or response.status_code != 422:
        return response

    chunks = [chunk async for chunk in response.body_iterator]
    body = b"".join(
        chunk if isinstance(chunk, bytes) else chunk.encode() for chunk in chunks
    )

    print(
        "\n[SLACK 422]",
        "\nResponse:",
        body.decode(errors="replace")[:2000],
        "\nRetry:",
        request.headers.get("x-slack-retry-num"),
        "\nReason:",
        request.headers.get("x-slack-retry-reason"),
        flush=True,
    )

    return Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        background=response.background,
    )
