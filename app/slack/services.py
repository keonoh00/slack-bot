from slack_sdk.signature import SignatureVerifier
from slack_sdk.web.async_client import AsyncWebClient

from app.config.env import env

slack = AsyncWebClient(
    token=env.slack.appToken.get_secret_value(),
)
verifier = SignatureVerifier(
    signing_secret=env.slack.botToken.get_secret_value(),
)
