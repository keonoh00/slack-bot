# slack-bot

A Slack bot that answers questions about your own PDF documents. Mention it in a
channel and it searches the indexed documents, answers in Korean with document
and page citations, and replies in the thread. Everything runs on your own
hardware: vLLM serves the language model and Qdrant stores the documents.

## How it works

```
Slack ── app_mention ──▶ FastAPI /slack/events ──▶ Redis ──▶ Celery worker
                         verify signature,                    │ load thread history
                         drop redeliveries                    │ LangGraph agent ⇄ document search ⇄ Qdrant
                                                              │ format the answer for Slack
Slack ◀──────────────── thread reply (chat.postMessage) ◀─────┘
```

1. The API verifies Slack's request signature, ignores Slack's redeliveries of
   an event it has already accepted, and queues the mention in Celery so Slack
   gets its response within 3 seconds.
2. The worker loads the earlier messages of the thread as conversation history,
   so follow-up questions work.
3. A LangGraph agent must search the documents before its first answer and may
   search again with a more specific query. Queries are embedded with
   sentence-transformers and matched in Qdrant.
4. A second model call reformats the answer for Slack. If the reformatted text
   contains a number the original answer did not, the original is sent instead.

The answer language and rules live in `SYSTEM_PROMPT` in
[app/agent/graph.py](app/agent/graph.py).

## Requirements

- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- Redis, Qdrant, and an OpenAI-compatible chat endpoint that supports tool
  calling. [docker-compose.yaml](docker-compose.yaml) runs all three; the vLLM
  container needs an NVIDIA GPU.
- A Slack workspace where you can install apps

## Slack app setup

1. Create an app at <https://api.slack.com/apps>.
2. Under **OAuth & Permissions**, add these bot token scopes:
   - `app_mentions:read`
   - `chat:write`
   - `channels:history` and `groups:history` (thread history in public and
     private channels)
   - `assistant:write` (optional: shows a "답변 작성 중..." status while the
     bot works)

   Install the app and copy the **Bot User OAuth Token** (`xoxb-...`).
3. Under **Basic Information**, copy the **Signing Secret**.
4. Under **Event Subscriptions**, enable events, set the request URL to
   `https://<your-host>/slack/events`, and subscribe to the `app_mention` bot
   event. The API must be running and reachable for Slack to accept the URL.
5. Invite the bot to the channels where it should answer.

## Configuration

Copy [.env.example](.env.example) and fill in the values. The poe tasks read
`.env.dev` for development and `.env.prod` for `prod-celery`.

```bash
cp .env.example .env.dev
```

The containers in `docker-compose.yaml` listen on `127.0.0.1` only. To reach them
from another machine, for example a GPU server on a private network, set
`DOCKER_BIND_ADDRESS` to that network interface's address. Do not use `0.0.0.0`:
Redis and Qdrant have no authentication, and ports published by Docker bypass
host firewalls such as ufw.

## Running locally

```bash
uv sync
uv run poe dev-docker                        # Redis, Qdrant and vLLM
uv run poe rag-index data/pdf/handbook.pdf   # index at least one document
uv run poe dev-api                           # API on http://localhost:8000
uv run poe dev-celery                        # worker, restarts on code changes
```

Slack has to reach `/slack/events` over HTTPS. `uv run poe dev-tunnel` runs a
Cloudflare Tunnel with `CLOUDFLARE_TUNNEL_TOKEN`; point the tunnel at
`http://localhost:8000`. Any other HTTPS tunnel works too.

## Indexing documents

```bash
uv run poe rag-index data/pdf/a.pdf data/pdf/b.pdf
uv run poe rag-index --recreate data/pdf/*.pdf
```

- Each PDF is split into chunks of about 500 tokens with pymupdf4llm and
  embedded with `QDRANT_EMBEDDING_MODEL_NAME`.
- Indexing a file again replaces its earlier chunks and leaves other files
  alone. Files are identified by file name, so two different files with the
  same name replace each other.
- `--recreate` drops the whole collection first. Use it after changing the
  embedding model.
- Indexing downloads the embedding model into the Hugging Face cache. The
  worker only loads it from that cache, so index once on the machine that runs
  the worker (or download the model there) before starting it.
- PDFs under `data/pdf/` are gitignored.

To try a search without Slack:

```bash
uv run --env-file .env.dev python -m app.agent.rag "검색할 질문"
```

## Deployment

The [Dockerfile](Dockerfile) builds an image that serves the API with uvicorn
on port 8000. The worker can run from the same image:

```bash
docker build -t slack-bot .
docker run -d --env-file .env.prod -p 127.0.0.1:8000:8000 slack-bot
docker run -d --env-file .env.prod \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  slack-bot .venv/bin/celery -A app.celery:celeryApp worker --concurrency=1 --loglevel=INFO
```

Inside a container, `localhost` is the container itself, so point `REDIS_URL`,
`VLLM_BASE_URL` and `QDRANT_URL` at addresses the container can reach. You can
also run the worker on the host with `uv run poe prod-celery`.

The worker logs each question's full answer at INFO level. If your documents
are confidential, treat the worker logs as confidential too.

## Development

```bash
uv run pytest
uv run ruff check
```

## Project layout

| Path | Contents |
| --- | --- |
| `app/api` | FastAPI routes: `/slack/events` and `/health` |
| `app/slack` | Slack client, event schemas, thread history, redelivery check |
| `app/celery` | Celery app and the task that answers a mention |
| `app/agent` | LangGraph agent, document search tool, Slack formatter |
| `app/config` | Settings read from the environment |
| `data/pdf/index.py` | PDF indexer |
