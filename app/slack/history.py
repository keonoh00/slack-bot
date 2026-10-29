from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.slack.services import slackClient


async def getThreadHistory(
    channel: str,
    threadTs: str,
    beforeTs: str,
) -> list[BaseMessage]:
    history: list[BaseMessage] = []
    cursor = None

    while True:
        response = await slackClient.conversations_replies(
            channel=channel,
            ts=threadTs,
            latest=beforeTs,
            limit=15,
            **({"cursor": cursor} if cursor else {}),
        )

        for message in response.get("messages", []):
            if message.get("type") != "message":
                continue

            if message.get("subtype") not in (None, "bot_message"):
                continue

            text = message.get("text", "").strip()

            if not text:
                continue

            if message.get("bot_id"):
                history.append(AIMessage(content=text))
            else:
                history.append(HumanMessage(content=text))

        cursor = response.get("response_metadata", {}).get("next_cursor")

        if not cursor:
            break

    return history
