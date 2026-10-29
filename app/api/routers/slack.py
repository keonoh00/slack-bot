import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.celery.tasks import replyToSlack
from app.slack.schemas import EventCallback, UrlVerification, slackPayloadAdapter
from app.slack.services import signatureVerifier

slackRouter = APIRouter(prefix="/slack", tags=["slack"])


@slackRouter.post("/events")
async def receiveEvents(request: Request) -> dict[str, str | bool]:
    body = await request.body()

    if not signatureVerifier.is_valid_request(body, request.headers):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = slackPayloadAdapter.validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid Slack payload") from exc

    if isinstance(payload, UrlVerification):
        return {"challenge": payload.challenge}

    if isinstance(payload, EventCallback):
        event = payload.event

        if event.type != "app_mention" or event.botId is not None:
            return {"ok": True}
        threadTs = event.threadTs or event.ts
        await asyncio.to_thread(
            replyToSlack.delay,
            event.channel,
            event.text,
            event.threadTs or event.ts,
            event.ts,
        )

    return {"ok": True}
