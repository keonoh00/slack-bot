from fastapi import APIRouter

slackRouter = APIRouter(prefix="/slack", tags=["slack"])


@slackRouter.post("/events")
async def handleEvents():
    return {"ok": True}


@slackRouter.post("/commands")
async def handleCommands():
    return {"ok": True}
