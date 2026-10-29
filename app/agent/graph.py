import os
from collections.abc import Sequence
from functools import lru_cache

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

SAFETY_MARGIN = 2048
MIN_OUTPUT_TOKENS = 1024
MIN_TOOL_LENGTH = 512
SYSTEM_PROMPT = """
You are a helpful AI assistant that answers questions in Korean.

When answering questions about reference documents:

1. Search using searchRAGTool before answering.
2. Verify that retrieved evidence matches the user's specific
   question, including years, versions, and other constraints.
3. If the evidence is insufficient, search again using a different
   or more specific query.
4. Perform up to 3 searches before concluding that information
   is unavailable.
5. Distinguish overall targets from year-specific targets.
6. Never invent numerical values or infer missing information
   from ambiguous evidence.
7. Cite document names and page numbers when available.

If the information is still unavailable after searching,
explain what could and could not be verified.
"""


def getOutputBudget(
    messages: Sequence[BaseMessage],
    tools: list[BaseTool],
) -> int:
    """Estimate available output tokens within the configured context window."""
    inputTokens = count_tokens_approximately(
        messages,
        tools=[convert_to_openai_tool(tool) for tool in tools],
        chars_per_token=2.0,
    )

    return int(os.environ["VLLM_MAX_LEN"]) - inputTokens - SAFETY_MARGIN


def reduceContext(messages: Sequence[BaseMessage]) -> list[BaseMessage] | None:
    """Remove older turns or shorten tool outputs to reduce context usage."""
    humanIndices = [
        i for i, message in enumerate(messages) if isinstance(message, HumanMessage)
    ]

    if len(humanIndices) >= 2:
        systemMessages = [
            message
            for message in messages[: humanIndices[0]]
            if isinstance(message, SystemMessage)
        ]
        return systemMessages + list(messages[humanIndices[1] :])

    for i in reversed(range(len(messages))):
        message = messages[i]

        if not isinstance(message, ToolMessage):
            continue

        if not isinstance(message.content, str):
            continue

        if len(message.content) <= MIN_TOOL_LENGTH:
            continue

        shortened = message.model_copy(
            update={
                "content": (
                    message.content[: len(message.content) // 2]
                    + "\n[일부 검색 결과 생략]"
                )
            }
        )

        return [*messages[:i], shortened, *messages[i + 1 :]]

    return None


@lru_cache(maxsize=1)
def buildAgent():
    from app.agent.rag import searchRAGTool
    from app.config.env import env

    tools: list[BaseTool] = [searchRAGTool]

    model = ChatOpenAI(
        model=env.vllm.MODEL,
        base_url=env.vllm.URL,
        api_key=env.vllm.API_KEY,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False,
            }
        },
    )

    modelWithTools = model.bind_tools(tools)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("messages"),
        ]
    )

    async def agent(state: MessagesState):

        messages: Sequence[BaseMessage] = prompt.format_messages(
            messages=state["messages"]
        )

        while True:
            maxOutputTokens = getOutputBudget(messages, tools)

            if maxOutputTokens >= MIN_OUTPUT_TOKENS:
                break

            reduced = reduceContext(messages)

            if reduced is None:
                return {
                    "messages": [
                        AIMessage(
                            content="입력 Context가 너무 길어 처리할 수 없습니다."
                        )
                    ]
                }

            messages = reduced

        response = await modelWithTools.bind(max_tokens=maxOutputTokens).ainvoke(
            messages
        )

        return {"messages": [response]}

    builder = StateGraph(MessagesState)

    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()


async def askAgent(text: str, history: list[BaseMessage] | None = None) -> str:
    messages = [*(history or []), HumanMessage(content=text)]

    result = await buildAgent().ainvoke({"messages": messages})

    return str(result["messages"][-1].content)
