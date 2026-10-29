import argparse
import os
from pathlib import Path

import pymupdf4llm
from qdrant_client import QdrantClient, models

QDRANT_URL = os.environ["QDRANT_URL"]
COLLECTION = os.environ["QDRANT_COLLECTION"]
MODEL_NAME = os.environ["QDRANT_EMBEDDING_MODEL_NAME"]


def ingestPdf(pdfPath: Path) -> None:
    from sentence_transformers import SentenceTransformer

    if not pdfPath.is_file():
        raise FileNotFoundError(pdfPath)

    document = pymupdf4llm.to_chunks(
        str(pdfPath),
        max_tokens=500,
        sentence_splitter="multilingual",
        table_mode="preserve",
        table_output="html",
        header_footer_mode="auto",
    )

    chunks = [chunk for chunk in document if chunk.text.strip()]

    if not chunks:
        raise ValueError("Text Extraction Failed")

    print(f"Chunks: {len(chunks)}")
    print(f"Diagnostics: {document.diagnostics}")

    encoder = SentenceTransformer(MODEL_NAME)

    dimension = encoder.get_embedding_dimension()

    if dimension is None:
        raise ValueError("Embedding Dimension cannot be verified")

    client = QdrantClient(url=QDRANT_URL)

    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(
            size=dimension,
            distance=models.Distance.COSINE,
        ),
    )

    batchSize = 32

    for start in range(0, len(chunks), batchSize):
        batch = chunks[start : start + batchSize]

        texts = [
            f"{' > '.join(chunk.metadata.section_path)}\n{chunk.text}"
            for chunk in batch
        ]

        vectors = encoder.encode_document(
            texts,
            batch_size=8,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        points = []

        for i, (chunk, vector) in enumerate(zip(batch, vectors)):
            points.append(
                models.PointStruct(
                    id=start + i,
                    vector=vector.tolist(),
                    payload={
                        "chunk_id": chunk.id,
                        "source": pdfPath.name,
                        "section": " > ".join(chunk.metadata.section_path),
                        "page_start": chunk.metadata.page_start,
                        "page_end": chunk.metadata.page_end,
                        "types": chunk.metadata.types,
                        "text": chunk.text,
                    },
                )
            )

        client.upload_points(
            collection_name=COLLECTION,
            points=points,
            wait=True,
        )

        print(f"Indexed: {min(start + batchSize, len(chunks))}/{len(chunks)}")

    print("PDF indexing completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()

    ingestPdf(args.pdf)
