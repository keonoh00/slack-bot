import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routers import slack as slackRoutes
from app.main import app
from app.slack.services import signatureVerifier


def signedHeaders(body: bytes, **extra: str) -> dict[str, str]:
    timestamp = str(int(time.time()))

    return {
        "Content-Type": "application/json",
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signatureVerifier.generate_signature(
            timestamp=timestamp,
            body=body,
        ),
        **extra,
    }


def mention(
    eventId: str = "Ev1",
    threadTs: str | None = None,
    botId: str | None = None,
) -> bytes:
    event = {
        "type": "app_mention",
        "channel": "C1",
        "user": "U1",
        "text": "<@B1> 올해 예산은?",
        "ts": "1700000000.000200",
    }

    if threadTs:
        event["thread_ts"] = threadTs

    if botId:
        event["bot_id"] = botId

    return json.dumps(
        {"type": "event_callback", "event_id": eventId, "event": event}
    ).encode()


@pytest.fixture
def queue(monkeypatch):
    state = SimpleNamespace(calls=[], claimed=set(), released=[], error=None)

    async def claimEvent(eventId: str) -> bool:
        if eventId in state.claimed:
            return False

        state.claimed.add(eventId)
        return True

    async def releaseEvent(eventId: str) -> None:
        state.claimed.discard(eventId)
        state.released.append(eventId)

    def delay(*args):
        if state.error:
            raise state.error

        state.calls.append(args)

    monkeypatch.setattr(slackRoutes, "claimEvent", claimEvent)
    monkeypatch.setattr(slackRoutes, "releaseEvent", releaseEvent)
    monkeypatch.setattr(slackRoutes, "replyToSlack", SimpleNamespace(delay=delay))

    return state


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_rejects_invalid_signature(client, queue):
    body = mention()
    headers = signedHeaders(body, **{"X-Slack-Signature": "v0=invalid"})

    response = client.post("/slack/events", content=body, headers=headers)

    assert response.status_code == 401
    assert queue.calls == []


def test_answers_url_verification(client, queue):
    body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()

    response = client.post("/slack/events", content=body, headers=signedHeaders(body))

    assert response.json() == {"challenge": "abc"}


def test_queues_mention_in_new_thread(client, queue):
    body = mention()

    response = client.post("/slack/events", content=body, headers=signedHeaders(body))

    assert response.json() == {"ok": True}
    assert queue.calls == [
        ("C1", "<@B1> 올해 예산은?", "1700000000.000200", "1700000000.000200")
    ]


def test_queues_mention_in_existing_thread(client, queue):
    body = mention(threadTs="1700000000.000100")

    client.post("/slack/events", content=body, headers=signedHeaders(body))

    assert queue.calls[0][2:] == ("1700000000.000100", "1700000000.000200")


def test_drops_redelivered_event(client, queue):
    body = mention()

    client.post("/slack/events", content=body, headers=signedHeaders(body))
    response = client.post(
        "/slack/events",
        content=body,
        headers=signedHeaders(body, **{"X-Slack-Retry-Num": "1"}),
    )

    assert response.json() == {"ok": True}
    assert len(queue.calls) == 1


def test_ignores_bot_mentions(client, queue):
    body = mention(botId="B2")

    response = client.post("/slack/events", content=body, headers=signedHeaders(body))

    assert response.json() == {"ok": True}
    assert queue.calls == []
    assert queue.claimed == set()


def test_releases_event_when_queueing_fails(client, queue):
    body = mention()
    queue.error = ConnectionError("broker unavailable")

    failed = client.post("/slack/events", content=body, headers=signedHeaders(body))

    assert failed.status_code == 500
    assert queue.released == ["Ev1"]

    queue.error = None
    retried = client.post(
        "/slack/events",
        content=body,
        headers=signedHeaders(body, **{"X-Slack-Retry-Num": "1"}),
    )

    assert retried.json() == {"ok": True}
    assert len(queue.calls) == 1
