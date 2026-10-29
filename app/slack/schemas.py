from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class UrlVerification(BaseModel):
    type: Literal["url_verification"]
    challenge: str


class SlackEvent(BaseModel):
    type: str
    channel: str | None = None
    user: str | None = None
    text: str | None = None
    ts: str | None = None
    subtype: str | None = None
    botId: str | None = Field(default=None, validation_alias="bot_id")
    threadTs: str | None = Field(default=None, validation_alias="thread_ts")


class EventCallback(BaseModel):
    type: Literal["event_callback"]
    eventId: str = Field(validation_alias="event_id")
    event: SlackEvent


class AppRateLimited(BaseModel):
    type: Literal["app_rate_limited"]
    minuteRateLimited: int = Field(validation_alias="minute_rate_limited")


type SlackPayload = Annotated[
    UrlVerification | EventCallback | AppRateLimited,
    Field(discriminator="type"),
]

slackPayloadAdapter = TypeAdapter(SlackPayload)


class ThreadMessage(BaseModel):
    user: str | None = None
    text: str = ""


class ThreadResponse(BaseModel):
    messages: list[ThreadMessage]
