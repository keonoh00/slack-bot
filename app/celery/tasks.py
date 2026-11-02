import asyncio
import atexit
import logging
from functools import lru_cache

from langchain_core.messages import BaseMessage

from app.agent.format.slack import formatForSlack, toSlackPayload
from app.agent.graph import askAgent
from app.celery import celeryApp
from app.slack.history import getThreadHistory
from app.slack.services import slackClient

logger = logging.getLogger(__name__)


async def generateReply(text: str, history: list[BaseMessage]) -> dict:
    answer = await askAgent(text, history)
    logger.info("Agent answer: %s", answer)

    formatted = await formatForSlack(text, answer)
    logger.info("Formatted answer: %s", formatted)

    return toSlackPayload(formatted)


async def _replyToSlack(channel: str, text: str, threadTs: str, messageTs: str):
    try:
        try:
            await slackClient.assistant_threads_setStatus(
                channel_id=channel,
                thread_ts=threadTs,
                status="답변 작성 중...",
                loading_messages=[
                    "질문을 분석하고 있어요",
                    "관련 문서를 검색하고 있어요",
                    "답변을 준비하고 있어요",
                ],
            )
        except Exception:
            logger.warning("Failed to set Slack status", exc_info=True)

        history = await getThreadHistory(channel, threadTs, messageTs)
        logger.info("Thread history loaded: %d messages", len(history))

        payload = await generateReply(text, history)

        await slackClient.chat_postMessage(
            channel=channel,
            thread_ts=threadTs,
            **payload,
        )
        logger.info("Slack reply sent")

    except Exception:
        logger.exception("Failed to reply to Slack")

        try:
            await slackClient.chat_postMessage(
                channel=channel,
                thread_ts=threadTs,
                text="요청 처리 중 오류가 발생했습니다.",
            )
        except Exception:
            logger.exception("Failed to send Slack error message")

        raise

    finally:
        try:
            await slackClient.assistant_threads_setStatus(
                channel_id=channel,
                thread_ts=threadTs,
                status="",
            )
        except Exception:
            logger.warning("Failed to clear Slack status", exc_info=True)


@lru_cache(maxsize=1)
def getRunner() -> asyncio.Runner:
    runner = asyncio.Runner()
    atexit.register(runner.close)
    return runner


@celeryApp.task
def replyToSlack(channel: str, text: str, threadTs: str, messageTs: str):
    getRunner().run(_replyToSlack(channel, text, threadTs, messageTs))
