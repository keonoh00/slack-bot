import logging
from functools import lru_cache
from typing import Annotated, TypedDict

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import trim_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)

MAX_INPUT_TOKENS = 12000
MAX_OUTPUT_TOKENS = 2048

SYSTEM_PROMPT = """
You are a helpful AI assistant that answers questions in Korean.

Use conversation history to understand follow-up questions.
Resolve references to previous questions and answers.

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

Never claim to have searched documents unless a tool was actually executed.

If the information is still unavailable after searching,
explain what could and could not be verified.
"""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@lru_cache(maxsize=1)
def buildAgent():
    from app.agent.rag import searchRAGTool
    from app.config.env import env

    tools = [searchRAGTool]

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

    modelWithTools = model.bind_tools(
        tools,
        tool_choice="auto",
    )

    modelWithRequiredTool = model.bind_tools(
        tools,
        tool_choice="required",
    )

    async def agent(state: AgentState):
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            *state["messages"],
        ]

        hasSearched = any(
            isinstance(message, ToolMessage) and message.name == searchRAGTool.name
            for message in state["messages"]
        )

        selectedModel = modelWithTools if hasSearched else modelWithRequiredTool

        response = await selectedModel.bind(
            max_tokens=MAX_OUTPUT_TOKENS,
        ).ainvoke(messages)

        logger.info("Tool calls: %s", response.tool_calls)
        logger.info("Invalid tool calls: %s", response.invalid_tool_calls)

        return {"messages": [response]}

    builder = StateGraph(AgentState)

    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()


async def askAgent(
    text: str,
    history: list[BaseMessage] | None = None,
) -> str:
    messages = trim_messages(
        [
            *(history or []),
            HumanMessage(content=text),
        ],
        max_tokens=MAX_INPUT_TOKENS,
        token_counter="approximate",
        strategy="last",
        start_on="human",
        end_on="human",
        allow_partial=False,
    )

    if not messages:
        return "입력 Context가 너무 길어 처리할 수 없습니다."

    logger.info(
        "Conversation context: %d messages",
        len(messages),
    )

    initialState: AgentState = {
        "messages": messages,
    }

    result = await buildAgent().ainvoke(initialState)

    for message in result["messages"]:
        if isinstance(message, ToolMessage):
            logger.info("Executed tool: %s", message.name)

    return str(result["messages"][-1].content)
