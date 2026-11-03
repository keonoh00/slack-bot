import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.celery.tasks import replyToSlack
from app.slack.schemas import EventCallback, UrlVerification, slackPayloadAdapter
from app.slack.services import signatureVerifier

logger = logging.getLogger(__name__)

slackRouter = APIRouter(prefix="/slack", tags=["slack"])


@slackRouter.post("/events")
async def receiveEvents(request: Request) -> dict[str, str | bool]:
    body = await request.body()

    if not signatureVerifier.is_valid_request(body, request.headers):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = slackPayloadAdapter.validate_json(body)
    except ValidationError as exc:
        logger.warning("Invalid Slack payload: %s", exc)
        raise HTTPException(status_code=422, detail="Invalid Slack payload") from exc

    if isinstance(payload, UrlVerification):
        return {"challenge": payload.challenge}

    event = getattr(payload, "event", None)

    logger.info(
        "event_id=%s type=%s ts=%s bot_id=%s retry=%s",
        getattr(payload, "eventId", None),
        getattr(event, "type", payload.type),
        getattr(event, "ts", None),
        getattr(event, "botId", None),
        request.headers.get("x-slack-retry-num"),
    )

    if isinstance(payload, EventCallback):
        event = payload.event

        if event.type != "app_mention" or event.botId is not None:
            return {"ok": True}

        threadTs = event.threadTs or event.ts
        await asyncio.to_thread(
            replyToSlack.delay,
            event.channel,
            event.text,
            threadTs,
            event.ts,
        )

    return {"ok": True}
