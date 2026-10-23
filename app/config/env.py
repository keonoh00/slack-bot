import os

from pydantic import BaseModel, SecretStr


class SlackSettings(BaseModel):
    appToken: SecretStr
    botToken: SecretStr


class RedisSettings(BaseModel):
    url: str


class EnvVariables(BaseModel):
    slack: SlackSettings
    redis: RedisSettings


env = EnvVariables(
    slack=SlackSettings(
        appToken=SecretStr(os.environ["SLACK_CODE_MASTER_APP_TOKEN"]),
        botToken=SecretStr(os.environ["SLACK_CODE_MASTER_BOT_TOKEN"]),
    ),
    redis=RedisSettings(
        url=os.environ["REDIS_URL"],
    ),
)
