"""Qdrant vector store — semantic memory for cycle summaries and market patterns."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import get_settings

settings = get_settings()

COLLECTION_CYCLES = "sfomo_cycles"
COLLECTION_PATTERNS = "sfomo_patterns"
VECTOR_SIZE = 1536  # text-embedding-3-small


class VectorStoreService:
    def __init__(self):
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        self._embeddings = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )

    async def ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        for name in [COLLECTION_CYCLES, COLLECTION_PATTERNS]:
            try:
                await self._client.get_collection(name)
            except Exception:
                await self._client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"[VectorStore] created collection: {name}")

    async def store_cycle_memory(
        self,
        cycle_id: str,
        content: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Embed and store a cycle summary."""
        try:
            vector = await self._embeddings.aembed_query(content)
            point = PointStruct(
                id=abs(hash(cycle_id)) % (10**12),
                vector=vector,
                payload={"content": content, **metadata},
            )
            await self._client.upsert(COLLECTION_CYCLES, points=[point])
        except Exception as e:
            logger.warning(f"[VectorStore] store_cycle_memory error: {e}")

    async def search_similar_cycles(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve similar historical cycles by semantic similarity."""
        try:
            vector = await self._embeddings.aembed_query(query)
            results = await self._client.search(
                collection_name=COLLECTION_CYCLES,
                query_vector=vector,
                limit=limit,
            )
            return [
                {"score": r.score, **r.payload}
                for r in results
            ]
        except Exception as e:
            logger.warning(f"[VectorStore] search error: {e}")
            return []

    async def close(self) -> None:
        await self._client.close()
