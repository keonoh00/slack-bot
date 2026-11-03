import os

# app.config.env reads these at import time; tests must never reach real services.
os.environ.update(
    SLACK_CODE_MASTER_BOT_TOKEN="xoxb-test",
    SLACK_CODE_MASTER_SIGNING_SECRET="test-signing-secret",
    REDIS_URL="redis://localhost:6379/15",
    VLLM_API_KEY="test",
    VLLM_BASE_URL="http://localhost:8001/v1",
    VLLM_MODEL="test-model",
    QDRANT_URL="http://localhost:6333",
    QDRANT_COLLECTION="test",
    QDRANT_EMBEDDING_MODEL_NAME="test-embedding-model",
)
