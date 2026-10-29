import logging
import re
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a Slack message formatter, not a research assistant.

Your task is to reformat an existing answer for readability in Slack.

Rules:
- Preserve the meaning, facts, numbers, dates, units, and sources.
- Never add new information, calculations, or assumptions.
- Preserve uncertainty and missing information.
- Start with the direct answer.
- Prefer concise paragraphs, headings, and bullet lists.
- Summarize large tables unless the user explicitly requests details.
- Keep tables when they are important to the user's request.
- Use standard Markdown supported by Slack Markdown blocks.
- Do not add introductions or commentary about formatting.
- Return only the formatted answer.
"""

NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


@lru_cache(maxsize=1)
def getSlackFormatter():
    from app.config.env import env

    model = ChatOpenAI(
        model=env.vllm.MODEL,
        base_url=env.vllm.URL,
        api_key=env.vllm.API_KEY,
        temperature=0,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False,
            }
        },
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "Question:\n{question}\n\nAnswer:\n{answer}"),
        ]
    )

    return prompt | model | StrOutputParser()


async def formatForSlack(question: str, answer: str) -> str:
    try:
        formatted = (
            await getSlackFormatter().ainvoke(
                {
                    "question": question,
                    "answer": answer,
                }
            )
        ).strip()
    except Exception:
        logger.exception("Slack formatting failed")
        return answer

    originalNumbers = set(NUMBER_PATTERN.findall(answer))
    formattedNumbers = set(NUMBER_PATTERN.findall(formatted))

    if not formatted or not formattedNumbers.issubset(originalNumbers):
        logger.warning("Slack formatter changed numeric values")
        return answer

    return formatted


def toSlackPayload(text: str) -> dict:
    if not text.strip():
        text = "답변을 생성하지 못했습니다."

    if len(text) > 12000:
        return {"text": text}

    return {
        "text": text[:300],
        "blocks": [
            {
                "type": "markdown",
                "text": text,
            }
        ],
    }
