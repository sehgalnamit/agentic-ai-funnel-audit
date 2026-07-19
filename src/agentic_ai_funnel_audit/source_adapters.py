from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .knowledge_ingestion import KnowledgeIngestionJob


@dataclass
class SourceRecord:
    title: str
    content: str
    metadata: dict[str, Any]


class SourceAdapter:
    source_type: str = "unknown"
    domain: str = "strategy"
    owner: str = "platform"
    source_system: str = "unknown"
    refresh_cadence: str = "daily"

    def fetch_records(self) -> list[SourceRecord]:
        raise NotImplementedError

    def build_jobs(self) -> list[KnowledgeIngestionJob]:
        jobs: list[KnowledgeIngestionJob] = []
        for record in self.fetch_records():
            jobs.append(
                KnowledgeIngestionJob(
                    domain=self.domain,
                    owner=self.owner,
                    source_system=self.source_system,
                    refresh_mode="async",
                    refresh_cadence=self.refresh_cadence,
                    content_type="markdown",
                    title=record.title,
                    content=record.content,
                    metadata=record.metadata,
                )
            )
        return jobs


class JsonFeedAdapter(SourceAdapter):
    """Loads source records from file path or HTTPS URL.

    Expected JSON shape: list[{
      "title": "...",
      "content": "...",
      "metadata": {...}
    }]
    """

    env_key: str = ""

    def fetch_records(self) -> list[SourceRecord]:
        location = os.getenv(self.env_key, "").strip()
        if not location:
            return []

        payload = _load_json(location)
        if not isinstance(payload, list):
            return []

        records: list[SourceRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "Untitled record")
            content = str(item.get("content") or "")
            metadata = item.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            records.append(SourceRecord(title=title, content=content, metadata=metadata))
        return records


class StrategyDocsAdapter(JsonFeedAdapter):
    source_type = "strategy_docs"
    domain = "strategy"
    owner = "strategy-office"
    source_system = "strategy-doc-repository"
    refresh_cadence = "monthly"
    env_key = "AGENTIC_SOURCE_STRATEGY_DOCS"


class DataCatalogAdapter(JsonFeedAdapter):
    source_type = "data_catalog"
    domain = "data"
    owner = "data-governance"
    source_system = "data-catalog"
    refresh_cadence = "weekly"
    env_key = "AGENTIC_SOURCE_DATA_CATALOG"


class CmdbAdapter(JsonFeedAdapter):
    source_type = "cmdb"
    domain = "technology"
    owner = "enterprise-architecture"
    source_system = "cmdb"
    refresh_cadence = "daily"
    env_key = "AGENTIC_SOURCE_CMDB"


class TelemetryFeedAdapter(JsonFeedAdapter):
    source_type = "telemetry"
    domain = "technology"
    owner = "platform-observability"
    source_system = "telemetry-warehouse"
    refresh_cadence = "daily"
    env_key = "AGENTIC_SOURCE_TELEMETRY"


class CrmFeedAdapter(JsonFeedAdapter):
    source_type = "crm"
    domain = "market"
    owner = "revenue-ops"
    source_system = "crm"
    refresh_cadence = "daily"
    env_key = "AGENTIC_SOURCE_CRM"


class MarketFeedAdapter(JsonFeedAdapter):
    source_type = "market_feed"
    domain = "market"
    owner = "market-intelligence"
    source_system = "market-feed"
    refresh_cadence = "daily"
    env_key = "AGENTIC_SOURCE_MARKET"


def build_default_adapters() -> list[SourceAdapter]:
    return [
        StrategyDocsAdapter(),
        DataCatalogAdapter(),
        CmdbAdapter(),
        TelemetryFeedAdapter(),
        CrmFeedAdapter(),
        MarketFeedAdapter(),
    ]


def _load_json(location: str) -> Any:
    if location.startswith("http://") or location.startswith("https://"):
        request = Request(location, headers={"User-Agent": "agentic-ai-funnel-audit/1.0"})
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    path = Path(location)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
