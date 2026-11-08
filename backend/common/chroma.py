from __future__ import annotations

import chromadb

from common.config import get_settings

_client: chromadb.ClientAPI | None = None
_collection = None


def get_collection():
    global _client, _collection
    if _collection is None:
        settings = get_settings()
        _client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        _collection = _client.get_or_create_collection(name=settings.chroma_collection, embedding_function=None)
    return _collection


def search(query_embedding: list[float], top_k: int, exclude_chunk_ids: list[str] | None = None) -> list[dict]:
    collection = get_collection()
    # Over-fetch when excluding ids, since Chroma has no server-side "not in id"
    # filter for the base query API - we filter the excluded ones out client-side.
    fetch_k = top_k + len(exclude_chunk_ids or [])
    result = collection.query(query_embeddings=[query_embedding], n_results=fetch_k)

    exclude = set(exclude_chunk_ids or [])
    hits = []
    ids = result["ids"][0]
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]
    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        if chunk_id in exclude:
            continue
        # The real deployment's `document_chunks` collection (change.md "CHROMA:
        # ใช้ document_chunks ไม่ใช่ evidence_chunks") stores metadata in
        # camelCase (documentId/chunkIndex), not the snake_case this originally
        # assumed - confirmed live: {"documentType", "documentId", "curriculumId",
        # "page", "chunkIndex"}, no "source_filename" field at all. Tries both
        # spellings so this also still works against any collection that does
        # use the old snake_case shape.
        document_id = metadata.get("documentId", metadata.get("document_id"))
        chunk_index = metadata.get("chunkIndex", metadata.get("chunk_index"))
        # No human-readable filename is stored in Chroma metadata for the real
        # data - only a documentId (a MongoDB ObjectId string, foreign key into
        # `documents`). Resolving the real fileName would need an extra Mongo
        # join per hit, out of scope for this fix - documentId is used directly
        # as the stable per-source identifier instead (never fabricated), which
        # is what source_filename is actually used for downstream (grouping +
        # citation matching), not necessarily a literal filename.
        source_filename = metadata.get("source_filename", document_id)
        hits.append(
            {
                "chunk_id": chunk_id,
                "text": document,
                "distance": distance,
                "document_id": document_id,
                "chunk_index": chunk_index,
                "source_filename": source_filename,
            }
        )
        if len(hits) >= top_k:
            break
    return hits
