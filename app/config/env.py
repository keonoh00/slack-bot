import os

from pydantic import BaseModel, SecretStr


class SlackSettings(BaseModel):
    BOT_TOKEN: SecretStr
    SIGNING_SECRET: SecretStr


class RedisSettings(BaseModel):
    url: str


class EnvVariables(BaseModel):
    slack: SlackSettings
    redis: RedisSettings


env = EnvVariables(
    slack=SlackSettings(
        BOT_TOKEN=SecretStr(os.environ["SLACK_CODE_MASTER_BOT_TOKEN"]),
        SIGNING_SECRET=SecretStr(os.environ["SLACK_CODE_MASTER_SIGNING_SECRET"]),
    ),
    redis=RedisSettings(
        url=os.environ["REDIS_URL"],
    ),
)
