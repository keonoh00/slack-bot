import argparse
import os
import uuid
from pathlib import Path

import pymupdf4llm
from qdrant_client import QdrantClient, models

QDRANT_URL = os.environ["QDRANT_URL"]
COLLECTION = os.environ["QDRANT_COLLECTION"]
MODEL_NAME = os.environ["QDRANT_EMBEDDING_MODEL_NAME"]


def ensureCollection(client: QdrantClient, dimension: int, recreate: bool) -> None:
    if recreate and client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)

    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )

    vectors = client.get_collection(COLLECTION).config.params.vectors

    if not isinstance(vectors, models.VectorParams) or vectors.size != dimension:
        raise ValueError(
            f"Collection {COLLECTION} does not match the embedding dimension "
            f"{dimension}. Run with --recreate to rebuild it."
        )

    client.create_payload_index(
        collection_name=COLLECTION,
        field_name="source",
        field_schema=models.PayloadSchemaType.KEYWORD,
        wait=True,
    )


def ingestPdf(pdfPath: Path, client: QdrantClient, encoder) -> None:
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

    print(f"{pdfPath.name} chunks: {len(chunks)}")
    print(f"Diagnostics: {document.diagnostics}")

    # Re-indexing a file replaces its previous chunks and leaves other files intact.
    client.delete(
        collection_name=COLLECTION,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source",
                        match=models.MatchValue(value=pdfPath.name),
                    )
                ]
            )
        ),
        wait=True,
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

        for i, (chunk, vector) in enumerate(zip(batch, vectors, strict=True)):
            points.append(
                models.PointStruct(
                    id=str(
                        uuid.uuid5(uuid.NAMESPACE_URL, f"{pdfPath.name}:{start + i}")
                    ),
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

    print(f"{pdfPath.name} indexing completed.")


def main() -> None:
    from sentence_transformers import SentenceTransformer

    parser = argparse.ArgumentParser(
        description="Index PDF documents into Qdrant for document search."
    )
    parser.add_argument("pdfs", type=Path, nargs="+")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop the collection and every indexed document before indexing",
    )
    args = parser.parse_args()

    encoder = SentenceTransformer(MODEL_NAME)
    dimension = encoder.get_embedding_dimension()

    if dimension is None:
        raise ValueError("Embedding Dimension cannot be verified")

    client = QdrantClient(url=QDRANT_URL)
    ensureCollection(client, dimension, args.recreate)

    for pdfPath in args.pdfs:
        ingestPdf(pdfPath, client, encoder)


if __name__ == "__main__":
    main()
