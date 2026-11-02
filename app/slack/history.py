from decimal import Decimal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.slack.services import slackClient


async def getThreadHistory(
    channel: str,
    threadTs: str,
    beforeTs: str,
) -> list[BaseMessage]:
    rawMessages = []
    cursor = None

    while True:
        response = await slackClient.conversations_replies(
            channel=channel,
            ts=threadTs,
            latest=beforeTs,
            inclusive=False,
            limit=15,
            **({"cursor": cursor} if cursor else {}),
        )

        rawMessages.extend(response.get("messages", []))

        cursor = response.get("response_metadata", {}).get("next_cursor")

        if not cursor:
            break

    # Ensure chronological ordering across all pages.
    rawMessages.sort(key=lambda message: Decimal(message.get("ts", "0")))

    history: list[BaseMessage] = []

    for message in rawMessages:
        if message.get("type") != "message":
            continue

        if message.get("subtype") not in (None, "bot_message"):
            continue

        if message.get("ts") == beforeTs:
            continue

        blocks = message.get("blocks", [])
        texts = []

        for block in blocks:
            if block.get("type") == "markdown":
                value = block.get("text")

            elif block.get("type") == "section":
                value = block.get("text")

                if isinstance(value, dict):
                    value = value.get("text")

            else:
                continue

            if isinstance(value, str) and value.strip():
                texts.append(value)

        text = "\n\n".join(texts).strip()

        if not text:
            text = (message.get("text") or "").strip()

        if not text:
            continue

        if message.get("bot_id") or message.get("subtype") == "bot_message":
            history.append(AIMessage(content=text))
        else:
            history.append(HumanMessage(content=text))

    return history
