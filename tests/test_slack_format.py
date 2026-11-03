import asyncio
from types import SimpleNamespace

from app.agent.format import slack as slackFormat
from app.agent.format.slack import formatForSlack, toSlackPayload

ANSWER = "올해 예산은 1,200억 원이고 목표 달성률은 35%입니다. (계획서 12쪽)"


def useFormatter(monkeypatch, result: str = "", error: Exception | None = None):
    async def ainvoke(_):
        if error:
            raise error

        return result

    monkeypatch.setattr(
        slackFormat,
        "getSlackFormatter",
        lambda: SimpleNamespace(ainvoke=ainvoke),
    )


def test_keeps_formatted_answer_with_same_numbers(monkeypatch):
    formatted = "*예산*: 1,200억 원\n- 목표 달성률: 35%\n- 출처: 계획서 12쪽"
    useFormatter(monkeypatch, result=formatted)

    assert asyncio.run(formatForSlack("예산은?", ANSWER)) == formatted


def test_falls_back_when_numbers_change(monkeypatch):
    useFormatter(monkeypatch, result="*예산*: 1,300억 원\n- 목표 달성률: 35%")

    assert asyncio.run(formatForSlack("예산은?", ANSWER)) == ANSWER


def test_falls_back_when_formatter_fails(monkeypatch):
    useFormatter(monkeypatch, error=RuntimeError("model unavailable"))

    assert asyncio.run(formatForSlack("예산은?", ANSWER)) == ANSWER


def test_falls_back_on_empty_output(monkeypatch):
    useFormatter(monkeypatch, result="   ")

    assert asyncio.run(formatForSlack("예산은?", ANSWER)) == ANSWER


def test_payload_uses_markdown_block():
    assert toSlackPayload("**답변**") == {
        "text": "**답변**",
        "blocks": [{"type": "markdown", "text": "**답변**"}],
    }


def test_payload_replaces_empty_answer():
    assert toSlackPayload(" ")["text"] == "답변을 생성하지 못했습니다."


def test_payload_skips_blocks_for_long_answer():
    text = "가" * 12001

    assert toSlackPayload(text) == {"text": text}
