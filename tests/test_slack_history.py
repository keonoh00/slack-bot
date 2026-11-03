import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from app.slack import history


class FakeSlackClient:
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.calls: list[dict] = []

    async def conversations_replies(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


def test_builds_history_across_pages(monkeypatch):
    client = FakeSlackClient(
        [
            {
                "messages": [
                    {"type": "message", "user": "U1", "ts": "1.0", "text": "첫 질문"},
                    {"type": "message", "user": "U1", "ts": "3.0", "text": "후속 질문"},
                ],
                "response_metadata": {"next_cursor": "page-2"},
            },
            {
                "messages": [
                    {
                        "type": "message",
                        "bot_id": "B1",
                        "ts": "2.0",
                        "text": "fallback",
                        "blocks": [
                            {"type": "markdown", "text": "첫 답변"},
                            {"type": "divider"},
                        ],
                    },
                    {
                        "type": "message",
                        "subtype": "channel_join",
                        "ts": "2.5",
                        "text": "joined",
                    },
                    {"type": "message", "user": "U1", "ts": "4.0", "text": "현재"},
                ],
            },
        ]
    )
    monkeypatch.setattr(history, "slackClient", client)

    messages = asyncio.run(history.getThreadHistory("C1", "1.0", "4.0"))

    assert [(type(message), message.content) for message in messages] == [
        (HumanMessage, "첫 질문"),
        (AIMessage, "첫 답변"),
        (HumanMessage, "후속 질문"),
    ]
    assert client.calls[1]["cursor"] == "page-2"
