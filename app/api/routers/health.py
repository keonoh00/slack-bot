from fastapi import APIRouter

healthRouter = APIRouter(prefix="/health")


@healthRouter.get("")
async def checkHealth():
    return {"status": "healthy"}
