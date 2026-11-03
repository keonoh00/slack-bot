import logging

from fastapi import FastAPI

from app.api.routers.health import healthRouter
from app.api.routers.slack import slackRouter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI()
app.include_router(slackRouter)
app.include_router(healthRouter)
