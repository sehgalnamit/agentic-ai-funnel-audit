from __future__ import annotations

from collections import defaultdict
import hashlib
import math
import os
import time
from typing import Any, Iterable


class HybridRetrievalEngine:
    """Hybrid lexical, vector, graph, and cache-backed retrieval.

    Local mode uses deterministic hashed embeddings and an in-process TTL cache.
    Set AGENTIC_RETRIEVAL_CACHE_BACKEND=redis and AGENTIC_REDIS_URL to share
    result caching across service instances.
    """

    def __init__(self, documents: Iterable[Any], vector_dimensions: int = 128) -> None:
        self.documents = list(documents)
        self.vector_dimensions = vector_dimensions
        self._vectors = {document.id: self._embed(self._document_text(document)) for document in self.documents}
        self._entity_index = self._build_entity_index()
        self._local_cache: dict[str, tuple[float, list[str]]] = {}
        self._redis = self._connect_redis()

    def search(
        self,
        domain: str,
        query: str,
        limit: int,
        tokenize: Any,
        make_hit: Any,
        access_context: dict[str, Any] | None = None,
    ) -> list[Any]:
        access_context = access_context or {}
        permitted = [document for document in self.documents if document.domain == domain and self._is_authorized(document, access_context)]
        cache_key = self._cache_key(domain, query, limit, access_context)
        cached_ids = self._get_cached_ids(cache_key)
        by_id = {document.id: document for document in permitted}
        if cached_ids is not None:
            return [make_hit(by_id[document_id], 0.0, set()) for document_id in cached_ids if document_id in by_id]

        query_tokens = tokenize(query)
        query_vector = self._embed(query)
        direct_scores: dict[str, float] = {}
        matched_entities: set[str] = set()

        for document in permitted:
            doc_tokens = tokenize(self._document_text(document))
            lexical_score = len(query_tokens & doc_tokens)
            vector_score = self._cosine(query_vector, self._vectors[document.id])
            if lexical_score == 0 and vector_score < 0.06:
                continue
            direct_scores[document.id] = lexical_score + vector_score * 3.0
            matched_entities.update(self._entities(document) & query_tokens)

        graph_scores: dict[str, float] = defaultdict(float)
        for entity in matched_entities:
            for document_id in self._entity_index.get(entity, set()):
                if document_id in by_id:
                    graph_scores[document_id] += 0.35

        ranked = sorted(
            direct_scores,
            key=lambda document_id: direct_scores[document_id] + graph_scores[document_id],
            reverse=True,
        )[:limit]
        self._cache_ids(cache_key, ranked)
        return [
            make_hit(
                by_id[document_id],
                direct_scores[document_id] + graph_scores[document_id],
                query_tokens & tokenize(self._document_text(by_id[document_id])),
            )
            for document_id in ranked
        ]

    def _document_text(self, document: Any) -> str:
        metadata_values: list[str] = []
        for value in document.metadata.values():
            metadata_values.extend(str(item) for item in value) if isinstance(value, list) else metadata_values.append(str(value))
        return " ".join([document.title, document.content, *metadata_values])

    def _build_entity_index(self) -> dict[str, set[str]]:
        index: dict[str, set[str]] = defaultdict(set)
        for document in self.documents:
            for entity in self._entities(document):
                index[entity].add(document.id)
        return index

    def _entities(self, document: Any) -> set[str]:
        entities = {document.domain.lower()}
        for key in ("owner", "source_system", "systems", "covered_sources", "themes", "business_capability"):
            value = document.metadata.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                if item:
                    entities.update(str(item).lower().replace("_", " ").split())
        return entities

    def _is_authorized(self, document: Any, access_context: dict[str, Any]) -> bool:
        allowed_roles = document.metadata.get("allowed_roles")
        if not allowed_roles:
            return True
        roles = set(access_context.get("roles") or [])
        if isinstance(allowed_roles, str):
            allowed_roles = [item.strip() for item in allowed_roles.split(",")]
        return bool(roles & set(allowed_roles))

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.vector_dimensions
        for token in text.lower().split():
            bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.vector_dimensions
            vector[bucket] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]

    def _cosine(self, left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))

    def _cache_key(self, domain: str, query: str, limit: int, access_context: dict[str, Any]) -> str:
        roles = ",".join(sorted(access_context.get("roles") or []))
        raw = f"{domain}|{query.lower()}|{limit}|{roles}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _connect_redis(self) -> Any | None:
        if os.getenv("AGENTIC_RETRIEVAL_CACHE_BACKEND", "local").lower() != "redis":
            return None
        try:
            import redis  # type: ignore
            return redis.from_url(os.environ["AGENTIC_REDIS_URL"], decode_responses=True)
        except Exception:
            return None

    def _get_cached_ids(self, key: str) -> list[str] | None:
        if self._redis is not None:
            raw = self._redis.get(f"agentic:retrieval:{key}")
            return raw.split(",") if raw else None
        entry = self._local_cache.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        return None

    def _cache_ids(self, key: str, document_ids: list[str]) -> None:
        ttl_seconds = int(os.getenv("AGENTIC_RETRIEVAL_CACHE_TTL_SECONDS", "300"))
        if self._redis is not None:
            self._redis.setex(f"agentic:retrieval:{key}", ttl_seconds, ",".join(document_ids))
            return
        self._local_cache[key] = (time.monotonic() + ttl_seconds, document_ids)
