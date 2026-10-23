from fastapi import FastAPI

from app.api.routers.health import healthRouter
from app.api.routers.slack import slackRouter

app = FastAPI()
app.include_router(slackRouter)
app.include_router(healthRouter)
