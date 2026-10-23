from app.common.text import normalizeText


async def processJob(text: str) -> None:
    message = normalizeText(text)
    print(f"Processing: {message}")
