from slack_sdk.signature import SignatureVerifier
from slack_sdk.web.async_client import AsyncWebClient

from app.config.env import env

slackClient = AsyncWebClient(
    token=env.slack.BOT_TOKEN.get_secret_value(),
)
signatureVerifier = SignatureVerifier(
    signing_secret=env.slack.SIGNING_SECRET.get_secret_value(),
)
