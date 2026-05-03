"""ChromaDB vector store for semantic symbol search in the knowledge graph.

Replaces text-based substring matching with embedding vectors, enabling
semantic similarity search across symbols by their names, signatures,
and docstrings.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..knowledge_graph.models import Symbol

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("ChromaDB not installed. Falling back to text-based search.")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    logger.warning("sentence-transformers not installed. Will use ChromaDB default embeddings.")


class ChromaSymbolStore:
    """Vector-backed symbol search using ChromaDB.

    Provides semantic search over codebase symbols. When symbols are indexed,
    their name + signature + docstring are combined into an embedding vector
    and stored in ChromaDB. Queries find semantically similar symbols even
    when keywords don't exactly match.

    If ChromaDB is not available, falls back to in-memory text search
    with JSON file persistence for survival across restarts.
    """

    COLLECTION_NAME = "shadow_engine_symbols"

    def __init__(
        self,
        persist_path: str | Path = "./.shadow-engine/chroma",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self._embedding_model_name = embedding_model
        self._embedder: Any = None

        if CHROMA_AVAILABLE:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        else:
            self._client = None
            self._collection = None

        self._fallback_symbols = self._load_fallback_json()

        if EMBEDDING_AVAILABLE:
            self._load_embedder()

    def _load_embedder(self) -> None:
        if EMBEDDING_AVAILABLE:
            try:
                self._embedder = SentenceTransformer(self._embedding_model_name)
                logger.info(f"Loaded embedding model: {self._embedding_model_name}")
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
                self._embedder = None

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if self._embedder is not None and EMBEDDING_AVAILABLE:
            try:
                embeddings = self._embedder.encode(texts, show_progress_bar=False)
                return [emb.tolist() for emb in embeddings]
            except Exception as e:
                logger.warning(f"Embedding generation failed: {e}. Using ChromaDB default.")
                return []
        return []

    def _symbol_text(self, symbol: Symbol) -> str:
        parts = [symbol.name, symbol.signature]
        if symbol.docstring:
            parts.append(symbol.docstring)
        return " | ".join(parts)

    def index_symbols(self, symbols: dict[str, Symbol]) -> int:
        if not symbols:
            return 0

        if self._collection is not None:
            ids: list[str] = []
            documents: list[str] = []
            metadatas: list[dict[str, Any]] = []
            texts_for_embedding: list[str] = []

            for sym_id, sym in symbols.items():
                ids.append(sym_id)
                doc_text = self._symbol_text(sym)
                documents.append(doc_text)
                texts_for_embedding.append(doc_text)
                metadatas.append({
                    "name": sym.name, "kind": sym.kind.value,
                    "file_path": sym.file_path, "complexity": sym.complexity_score,
                })

            embeddings = self._encode(texts_for_embedding) if self._embedder else []

            try:
                kwargs: dict[str, Any] = {"ids": ids, "documents": documents, "metadatas": metadatas}
                if embeddings:
                    kwargs["embeddings"] = embeddings
                self._collection.upsert(**kwargs)
            except Exception as e:
                logger.warning(f"ChromaDB upsert failed: {e}. Persisting to JSON fallback.")
                self._write_fallback_json(ids, documents, metadatas)
                self._collection = None
                self._fallback_symbols = list(zip(ids, symbols.values()))
                return len(ids)
            return len(ids)
        else:
            self._fallback_symbols = list(symbols.items())
            return len(self._fallback_symbols)

    # Fix: search() now accepts optional store for full symbol enrichment
    def search(
        self, query: str, top_k: int = 20, kind_filter: str | None = None,
        store: Any = None,
    ) -> list[tuple[Symbol, float]]:
        """Semantic search for symbols.

        Args:
            query: Natural language search query
            top_k: Maximum results to return
            kind_filter: Optional symbol kind filter
            store: Optional store to enrich skeleton symbols with full data

        Returns:
            List of (Symbol, relevance_score) tuples, sorted by relevance
        """
        raw_results = self._search_raw(query, top_k, kind_filter)

        # Fix #2.2: Enrich skeleton symbols with full data from store
        if store is not None and hasattr(store, 'get_symbol'):
            enriched: list[tuple[Symbol, float]] = []
            for skeleton_sym, score in raw_results:
                full_sym = store.get_symbol(skeleton_sym.id)
                if full_sym is not None:
                    enriched.append((full_sym, score))
                else:
                    enriched.append((skeleton_sym, score))
            return enriched
        return raw_results

    def _search_raw(
        self, query: str, top_k: int = 20, kind_filter: str | None = None
    ) -> list[tuple[Symbol, float]]:
        if self._collection is not None:
            where_filter: dict[str, Any] | None = None
            if kind_filter:
                where_filter = {"kind": kind_filter}

            query_embeddings = self._encode([query]) if self._embedder else []
            kwargs: dict[str, Any] = {"query_texts": [query], "n_results": top_k}
            if query_embeddings:
                kwargs["query_embeddings"] = query_embeddings
            if where_filter:
                kwargs["where"] = where_filter

            try:
                results = self._collection.query(**kwargs)
            except Exception as e:
                logger.warning(f"ChromaDB query failed: {e}. Falling back to text search.")
                return self._fallback_search(query, top_k, kind_filter)

            if not results or not results.get("ids") or not results["ids"][0]:
                return []

            output: list[tuple[Symbol, float]] = []
            for i, sym_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                similarity = 1.0 - (float(distance) / 2.0) if distance is not None else 1.0
                sym = Symbol(
                    id=sym_id, name=metadata.get("name", "unknown"),
                    kind=metadata.get("kind", "function"),
                    file_path=metadata.get("file_path", ""),
                    line_start=0, line_end=0,
                    complexity_score=float(metadata.get("complexity", 0)),
                )
                output.append((sym, similarity))
            return output
        else:
            return self._fallback_search(query, top_k, kind_filter)

    def _write_fallback_json(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        import json as _json
        fallback_path = self.persist_path / "chroma_fallback.json"
        data = [{"id": ids[i], "document": documents[i] if i < len(documents) else "", "metadata": metadatas[i] if i < len(metadatas) else {}} for i in range(len(ids))]
        try:
            fallback_path.write_text(_json.dumps(data, indent=2))
        except Exception:
            pass

    def _load_fallback_json(self) -> list[tuple[str, Symbol]]:
        import json as _json
        fallback_path = self.persist_path / "chroma_fallback.json"
        if not fallback_path.exists():
            return []
        try:
            data = _json.loads(fallback_path.read_text())
            return [(
                entry["id"],
                Symbol(
                    id=entry["id"], name=entry.get("metadata", {}).get("name", "unknown"),
                    kind=entry.get("metadata", {}).get("kind", "function"),
                    file_path=entry.get("metadata", {}).get("file_path", ""),
                    line_start=0, line_end=0,
                    complexity_score=float(entry.get("metadata", {}).get("complexity", 0)),
                ),
            ) for entry in data]
        except Exception:
            return []

    def _fallback_search(self, query: str, top_k: int, kind_filter: str | None = None) -> list[tuple[Symbol, float]]:
        query_lower = query.lower()
        scored: list[tuple[Symbol, float]] = []
        for sym_id, sym in self._fallback_symbols:
            if kind_filter and sym.kind.value != kind_filter:
                continue
            text = self._symbol_text(sym).lower()
            score = sum(1 for word in query_lower.split() if word in text) / max(len(query_lower.split()), 1)
            if score > 0:
                scored.append((sym, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete_symbol(self, symbol_id: str) -> None:
        if self._collection is not None:
            try:
                self._collection.delete(ids=[symbol_id])
            except Exception:
                pass
        else:
            self._fallback_symbols = [(sid, sym) for sid, sym in self._fallback_symbols if sid != symbol_id]

    def count(self) -> int:
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                return len(self._fallback_symbols)
        return len(self._fallback_symbols)

    def clear(self) -> None:
        if self._collection is not None:
            try:
                self._client.delete_collection(self.COLLECTION_NAME)
                self._collection = self._client.get_or_create_collection(
                    name=self.COLLECTION_NAME, metadata={"hnsw:space": "cosine"},
                )
            except Exception:
                pass
        else:
            self._fallback_symbols.clear()