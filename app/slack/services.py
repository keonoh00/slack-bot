from redis.asyncio import Redis
from slack_sdk.signature import SignatureVerifier
from slack_sdk.web.async_client import AsyncWebClient

from app.config.env import env

EVENT_TTL_SECONDS = 60 * 60

slackClient = AsyncWebClient(
    token=env.slack.BOT_TOKEN.get_secret_value(),
)
signatureVerifier = SignatureVerifier(
    signing_secret=env.slack.SIGNING_SECRET.get_secret_value(),
)
redisClient = Redis.from_url(env.redis.url)


async def claimEvent(eventId: str) -> bool:
    # Slack redelivers events it considers unacknowledged; only the first claim wins.
    return bool(
        await redisClient.set(
            f"slack:event:{eventId}",
            1,
            nx=True,
            ex=EVENT_TTL_SECONDS,
        )
    )


async def releaseEvent(eventId: str) -> None:
    await redisClient.delete(f"slack:event:{eventId}")
