from slack_sdk.signature import SignatureVerifier
from slack_sdk.web.async_client import AsyncWebClient

from app.config.env import env
from app.slack.schemas import ThreadResponse

slackClient = AsyncWebClient(
    token=env.slack.BOT_TOKEN.get_secret_value(),
)
signatureVerifier = SignatureVerifier(
    signing_secret=env.slack.SIGNING_SECRET.get_secret_value(),
)


async def sendMessage(channel: str, text: str) -> None:
    await slackClient.chat_postMessage(
        channel=channel,
        text=text,
    )


async def replyWithContext(channel: str, threadTs: str) -> None:
    response = await slackClient.conversations_replies(
        channel=channel,
        ts=threadTs,
        limit=20,
    )

    thread = ThreadResponse.model_validate(response.data)

    for message in thread.messages:
        print(f"{message.user}: {message.text}")

    await slackClient.chat_postMessage(
        channel=channel,
        thread_ts=threadTs,
        text=f"I found {len(thread.messages)} messages in this thread.",
    )
