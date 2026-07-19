from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass
class KnowledgeIngestionJob:
    domain: str
    owner: str
    source_system: str
    refresh_mode: str
    refresh_cadence: str
    content_type: str
    title: str
    content: str
    metadata: dict[str, Any]
    created_at: str | None = None

    def to_snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at or datetime.now(timezone.utc).isoformat()
        return payload


class SnapshotKnowledgeWriter:
    def __init__(self, root: Path):
        self.root = root

    async def ingest(self, job: KnowledgeIngestionJob) -> Path:
        domain_root = self.root / job.domain
        domain_root.mkdir(parents=True, exist_ok=True)
        filename = f"{_slugify(job.title)}.json"
        path = domain_root / filename
        path.write_text(json.dumps(job.to_snapshot(), indent=2), encoding="utf-8")
        return path


class KnowledgeSyncPlanner:
    def __init__(self) -> None:
        self.domain_contracts = {
            "strategy": {
                "owner": "strategy-office",
                "source_examples": ["okr export", "portfolio planning deck", "strategy memo"],
                "recommended_refresh": "monthly",
            },
            "data": {
                "owner": "data-governance",
                "source_examples": ["data catalog", "quality dashboard", "lineage export"],
                "recommended_refresh": "weekly",
            },
            "technology": {
                "owner": "enterprise-architecture",
                "source_examples": ["cmdb", "telemetry warehouse", "architecture review register"],
                "recommended_refresh": "daily",
            },
            "market": {
                "owner": "market-intelligence",
                "source_examples": ["analyst feed", "crm notes", "win-loss summary"],
                "recommended_refresh": "daily",
            },
            "governance": {
                "owner": "risk-office",
                "source_examples": ["policy repository", "control attestation", "privacy review system"],
                "recommended_refresh": "monthly",
            },
        }

    def describe(self) -> dict[str, Any]:
        return {
            "ingestion_mode": "async_source_adapters_and_snapshots",
            "domains": self.domain_contracts,
        }


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "snapshot"
