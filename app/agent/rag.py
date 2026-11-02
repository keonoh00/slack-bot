import argparse
import asyncio
import json
import logging
import threading
from functools import lru_cache

from langchain_core.messages import ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import tool
from qdrant_client import AsyncQdrantClient

from app.config.env import env

logger = logging.getLogger(__name__)

MODEL_NAME = env.qdrant.MODEL
COLLECTION = env.qdrant.COLLECTION
QDRANT_URL = env.qdrant.URL
MAX_RAG_TOKENS = 2500

embeddingLock = threading.Lock()


@lru_cache(maxsize=1)
def getEncoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        MODEL_NAME,
        local_files_only=True,
    )


def embedQuery(query: str) -> list[float]:
    with embeddingLock:
        return (
            getEncoder()
            .encode_query(
                query,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            .tolist()
        )


def limitResults(results: list[dict]) -> list[dict]:
    selected = []

    for result in results:
        candidate = selected + [result]

        tokens = count_tokens_approximately(
            [
                ToolMessage(
                    content=json.dumps(candidate, ensure_ascii=False),
                    tool_call_id="rag",
                )
            ],
            chars_per_token=2.0,
        )

        if tokens > MAX_RAG_TOKENS:
            break

        selected.append(result)

    return selected


async def _searchDocument(
    query: str,
    limit: int = 5,
) -> list[dict]:
    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    if limit < 1:
        raise ValueError("Search limit must be greater than zero.")

    logger.info("Generating query embedding")

    vector = await asyncio.to_thread(embedQuery, query)

    logger.info("Query embedding generated")

    client = AsyncQdrantClient(url=QDRANT_URL)

    try:
        response = await client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
        )
    finally:
        await client.close()

    results = [
        {
            "score": point.score,
            **(point.payload or {}),
        }
        for point in response.points
    ]

    selected = limitResults(results)

    logger.info(
        "RAG retrieved %d results, retained %d",
        len(results),
        len(selected),
    )

    return selected


@tool
async def searchRAGTool(query: str, limit: int = 5) -> list[dict]:
    """
    Search indexed documents for factual information about projects,
    budgets, schedules, targets, and technical requirements.
    Use specific queries with relevant context and constraints.
    """
    return await _searchDocument(query, limit)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search indexed PDF documents in Qdrant."
    )

    parser.add_argument(
        "query",
        help="Natural language search query",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of results (default: 5)",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be greater than zero")

    results = await _searchDocument(args.query, args.limit)

    if not results:
        print("No results found.")
        return

    for i, result in enumerate(results, start=1):
        print(f"\n{'=' * 20} Result {i} {'=' * 20}")
        print(f"Score: {result['score']:.4f}")
        print(f"Source: {result.get('source', '')}")
        print(f"Section: {result.get('section', '')}")
        print(
            f"Pages: {result.get('page_start', '?')}-" f"{result.get('page_end', '?')}"
        )
        print(f"\n{result.get('text', '')}")


if __name__ == "__main__":
    asyncio.run(main())
