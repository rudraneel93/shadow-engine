"""Open-Inspect Integration — Async bridge between Shadow Engineer and Open-Inspect.

Provides async callbacks for session lifecycle:
1. Before spawn: enrich prompt with KG context + approach suggestion
2. After complete: ingest results into learning engine
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..main import ShadowEngine

logger = logging.getLogger(__name__)


class OpenInspectBridge:
    """Async bridge between Shadow Engineer and Open-Inspect.

    Usage:
        bridge = OpenInspectBridge(repo_path="/path/to/repo")
        enriched = await bridge.enrich_session_config(original_config)
        result = await bridge.ingest_session_result(completed_data)
    """

    def __init__(self, repo_path: str | Path = ".", storage_path: str | Path | None = None):
        self.repo_path = Path(repo_path).resolve()
        self.storage_path = Path(storage_path) if storage_path else self.repo_path / ".shadow-engine"
        self.engine = ShadowEngine(storage_path=self.storage_path, repo_path=self.repo_path)

    def bootstrap_if_needed(self) -> dict[str, Any]:
        stats = self.engine.get_stats()
        if stats["total_symbols"] == 0:
            return self.engine.bootstrap()
        return {"status": "already_bootstrapped", **stats}

    # Fix #12: Async enrichment — runs blocking I/O in a thread pool
    async def enrich_session_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Enrich session config with KG context and approach suggestion (async-safe)."""
        prompt = config.get("prompt", "")
        if not prompt:
            return config

        loop = asyncio.get_running_loop()
        context = await loop.run_in_executor(None, self.engine.get_context, prompt)
        suggestion = await loop.run_in_executor(None, self.engine.suggest, prompt)

        logger.info(f"KG context: {context.count(chr(10))} lines, approach: {suggestion['recommended_approach'][:80]}...")

        enriched = dict(config)
        enriched["kg_context"] = context
        enriched["suggested_approach"] = suggestion["recommended_approach"]
        enriched["problem_type"] = suggestion["problem_type"]
        enriched["classification_confidence"] = suggestion.get("classification_confidence", 0.0)
        if suggestion.get("best_model") and suggestion["best_model"] != "unknown":
            enriched["suggested_model"] = suggestion["best_model"]
        if context:
            enriched["prompt"] = context + "\n\n" + prompt
        return enriched

    # Fix #12: Async ingestion — runs store writes in a thread pool
    async def ingest_session_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Ingest session result into learning engine (async-safe)."""
        outcome_map = {
            "completed": "success", "merged": "success", "failed": "failure",
            "error": "failure", "rejected": "rejected", "abandoned": "abandoned",
            "timeout": "failure",
        }
        outcome = outcome_map.get(result.get("outcome", "failure"), result.get("outcome", "failure"))
        test_results = result.get("test_results", {})
        if not test_results and "tests_passed" in result:
            passed, failed = result.get("tests_passed", 0), result.get("tests_failed", 0)
            test_results = {"total": passed + failed, "passed": passed, "failed": failed}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.engine.record_result(
                session_id=result.get("session_id", ""),
                outcome=outcome,
                prompt=result.get("prompt", ""),
                approach=result.get("approach", ""),
                model=result.get("model", "default"),
                pr_url=result.get("pr_url"),
                files_changed=result.get("files_changed", []),
                test_results=test_results,
                review_comments=result.get("review_comments", []),
                duration_seconds=result.get("duration_seconds", result.get("duration", 0.0)),
                token_count=result.get("token_count", result.get("tokens", 0)),
            ),
        )

    async def get_context(self, task: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.engine.get_context, task)

    async def get_suggestion(self, task: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.engine.suggest, task)

    async def get_report(self) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.engine.get_report)

    async def get_stats(self) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.engine.get_stats)


# Convenience factory functions
def create_enrich_hook(repo_path: str | Path = ".") -> Any:
    bridge = OpenInspectBridge(repo_path=repo_path)
    bridge.bootstrap_if_needed()
    return bridge.enrich_session_config


def create_ingest_hook(repo_path: str | Path = ".") -> Any:
    bridge = OpenInspectBridge(repo_path=repo_path)
    return bridge.ingest_session_result