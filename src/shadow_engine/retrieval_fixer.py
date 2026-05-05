"""Retrieval-Augmented Fixer — simple RAG for bug fixes.

Replaces the failed pattern-extraction/causal-inference architecture with
a dead-simple approach:

1. Store successful bug-fix pairs (bug_signature, diff) in ChromaDB
2. On new bug, find top-3 most similar past bugs using embeddings
3. Inject past successful diffs into the LLM prompt

No causal inference, no Bayesian prediction, no debate engine.
Just: similar bug → similar fix.

This is the architecture that can actually be proven to work.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False
    SentenceTransformer = None  # type: ignore


class RetrievalAugmentedFixer:
    """Stores and retrieves successful bug-fix pairs using vector similarity.

    Uses sentence-transformers for embeddings and ChromaDB for storage.
    Falls back to dummy-mode if dependencies aren't available.
    """

    def __init__(
        self,
        chroma_store: Any | None = None,
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self._chroma = chroma_store
        self._embedder = None
        self._model_name = embedding_model
        self._available = False

        if _ST_AVAILABLE and chroma_store is not None:
            try:
                self._embedder = SentenceTransformer(embedding_model)
                self._available = True
                logger.info(f"RetrievalAugmentedFixer: loaded {embedding_model}")
            except Exception as e:
                logger.warning(f"RetrievalAugmentedFixer: could not load embedder: {e}")
        else:
            logger.info("RetrievalAugmentedFixer: running in dummy mode (no sentence-transformers or ChromaDB)")

        # In-memory fallback when ChromaDB isn't available
        self._memory_store: list[dict] = []

    @property
    def available(self) -> bool:
        return self._available

    def add_successful_fix(
        self,
        bug_id: str,
        bug_signature: str,
        diff: str,
        function_name: str = "",
    ) -> None:
        """Store a successful bug-fix pair.

        Args:
            bug_id: Unique identifier for this bug.
            bug_signature: Description of the bug (function code + test failures).
            diff: The unified diff that fixed the bug.
            function_name: Optional function name for tagging.
        """
        metadata = {
            "bug_id": bug_id,
            "bug_signature": bug_signature[:2000],  # Truncate for storage
            "diff": diff[:3000],
            "function_name": function_name,
        }

        if self._available and self._chroma is not None and self._embedder is not None:
            try:
                embedding = self._embedder.encode(bug_signature).tolist()
                collection = self._chroma._client.get_or_create_collection("successful_fixes")
                collection.add(
                    ids=[bug_id],
                    embeddings=[embedding],
                    metadatas=[metadata],
                )
                return
            except Exception as e:
                logger.debug(f"ChromaDB add failed, using memory fallback: {e}")

        # Fallback: in-memory store
        self._memory_store.append(metadata)

    def get_similar_fixes(self, current_bug_signature: str, n: int = 3) -> list["SimilarFix"]:
        """Retrieve the top N most similar past successful fixes.

        Args:
            current_bug_signature: Description of the current bug.
            n: Number of similar fixes to return.

        Returns:
            List of SimilarFix objects, sorted by similarity (highest first).
        """
        if self._available and self._chroma is not None and self._embedder is not None:
            try:
                embedding = self._embedder.encode(current_bug_signature).tolist()
                collection = self._chroma._client.get_or_create_collection("successful_fixes")
                if collection.count() == 0:
                    return []

                results = collection.query(query_embeddings=[embedding], n_results=min(n, collection.count()))
                similar = []
                if results["metadatas"] and results["metadatas"][0]:
                    for i, meta in enumerate(results["metadatas"][0]):
                        distance = results["distances"][0][i] if results.get("distances") else 1.0
                        similarity = 1.0 / (1.0 + distance) if distance else 1.0
                        similar.append(SimilarFix(
                            bug_signature=meta.get("bug_signature", "")[:500],
                            diff=meta.get("diff", ""),
                            function_name=meta.get("function_name", ""),
                            similarity=round(similarity, 3),
                        ))
                return similar
            except Exception as e:
                logger.debug(f"ChromaDB query failed, using memory fallback: {e}")

        # Fallback: simple text-based similarity on in-memory store
        if not self._memory_store:
            return []

        # Use simple word overlap as similarity
        current_words = set(current_bug_signature.lower().split())
        scored = []
        for meta in self._memory_store:
            stored_words = set(meta["bug_signature"].lower().split())
            overlap = len(current_words & stored_words) / max(len(current_words | stored_words), 1)
            scored.append((overlap, meta))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SimilarFix(
                bug_signature=m["bug_signature"][:500],
                diff=m["diff"],
                function_name=m.get("function_name", ""),
                similarity=round(s, 3),
            )
            for s, m in scored[:n]
        ]

    def count(self) -> int:
        """Return number of stored successful fixes."""
        if self._available and self._chroma is not None:
            try:
                collection = self._chroma._client.get_or_create_collection("successful_fixes")
                return collection.count()
            except Exception:
                pass
        return len(self._memory_store)


class SimilarFix:
    """A retrieved similar bug-fix pair."""

    def __init__(
        self,
        bug_signature: str,
        diff: str,
        function_name: str = "",
        similarity: float = 0.0,
    ):
        self.bug_signature = bug_signature
        self.diff = diff
        self.function_name = function_name
        self.similarity = similarity

    def format_for_prompt(self) -> str:
        """Format this fix for injection into an LLM prompt."""
        return (
            f"Similar bug (similarity: {self.similarity:.2f}):\n"
            f"  Function: {self.function_name}\n"
            f"  Context: {self.bug_signature[:200]}\n"
            f"  Fix:\n```diff\n{self.diff[:500]}\n```\n"
        )


def format_retrieval_context(similar_fixes: list[SimilarFix]) -> str:
    """Format retrieved fixes as a prompt section."""
    if not similar_fixes:
        return ""

    lines = [
        "Here are similar bugs that were fixed successfully in the past:",
        "",
    ]
    for i, fix in enumerate(similar_fixes, 1):
        lines.append(f"Example {i} (similarity: {fix.similarity:.2f}):")
        lines.append(f"  Function: {fix.function_name}")
        lines.append(f"  Bug context: {fix.bug_signature[:300]}")
        lines.append(f"  Fix applied:")
        lines.append(f"```diff")
        lines.append(fix.diff[:800])
        lines.append(f"```")
        lines.append("")

    return "\n".join(lines)