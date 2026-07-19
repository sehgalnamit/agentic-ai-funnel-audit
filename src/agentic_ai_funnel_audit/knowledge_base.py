from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]{1,}", re.IGNORECASE)


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "") if len(token) >= 3}


def _coerce_value(value: str) -> Any:
    raw = value.strip()
    if not raw:
        return ""
    if "," in raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        return raw


@dataclass
class KnowledgeDocument:
    id: str
    domain: str
    title: str
    content: str
    metadata: dict[str, Any]


@dataclass
class KnowledgeHit:
    document: KnowledgeDocument
    score: float
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.document.id,
            "domain": self.document.domain,
            "title": self.document.title,
            "score": round(self.score, 2),
            "excerpt": self.excerpt,
            "metadata": self.document.metadata,
        }


@dataclass
class KnowledgeDomainStatus:
    domain: str
    owner: str
    refresh_mode: str
    refresh_cadence: str
    source_system: str
    document_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "owner": self.owner,
            "refresh_mode": self.refresh_mode,
            "refresh_cadence": self.refresh_cadence,
            "source_system": self.source_system,
            "document_count": self.document_count,
        }


class DemoKnowledgeBase:
    def __init__(self, documents: Iterable[KnowledgeDocument]):
        self.documents = list(documents)

    @classmethod
    def from_directory(cls, root: Path) -> "DemoKnowledgeBase":
        documents: list[KnowledgeDocument] = []
        for path in sorted(root.rglob("*.md")):
            domain = path.parent.name.lower()
            text = path.read_text(encoding="utf-8")
            metadata, content = _split_frontmatter(text)
            title = metadata.get("title") or _title_from_content(content) or path.stem.replace("-", " ").title()
            documents.append(
                KnowledgeDocument(
                    id=f"{domain}/{path.stem}",
                    domain=domain,
                    title=str(title),
                    content=content.strip(),
                    metadata=metadata,
                )
            )
        return cls(documents)

    def search(self, domain: str, query: str, limit: int = 3) -> list[KnowledgeHit]:
        domain_docs = [doc for doc in self.documents if doc.domain == domain]
        query_tokens = _tokenize(query)
        hits: list[KnowledgeHit] = []
        for document in domain_docs:
            searchable = " ".join(
                [document.title, document.content, " ".join(_flatten_metadata(document.metadata))]
            )
            doc_tokens = _tokenize(searchable)
            overlap = query_tokens & doc_tokens
            if not overlap:
                continue
            metadata_score = sum(
                value for key, value in document.metadata.items() if key.endswith("_score") and isinstance(value, int)
            )
            score = float(len(overlap)) + (metadata_score / 10.0)
            hits.append(KnowledgeHit(document=document, score=score, excerpt=_build_excerpt(document.content, overlap)))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]

    def grouped_documents(self) -> dict[str, list[KnowledgeDocument]]:
        grouped: dict[str, list[KnowledgeDocument]] = {}
        for document in self.documents:
            grouped.setdefault(document.domain, []).append(document)
        return grouped

    def domain_statuses(self) -> list[KnowledgeDomainStatus]:
        statuses: list[KnowledgeDomainStatus] = []
        for domain, documents in self.grouped_documents().items():
            first = documents[0]
            statuses.append(
                KnowledgeDomainStatus(
                    domain=domain,
                    owner=str(first.metadata.get("owner", "unknown")),
                    refresh_mode=str(first.metadata.get("refresh_mode", "async")),
                    refresh_cadence=str(first.metadata.get("refresh_cadence", "daily")),
                    source_system=str(first.metadata.get("source_system", "enterprise documents")),
                    document_count=len(documents),
                )
            )
        return sorted(statuses, key=lambda status: status.domain)


_cached_demo_kb: DemoKnowledgeBase | None = None


def load_demo_knowledge_base(root: Path | None = None) -> DemoKnowledgeBase:
    global _cached_demo_kb
    kb_root = root or Path(__file__).resolve().parents[2] / "demo_kb"
    if _cached_demo_kb is None:
        _cached_demo_kb = DemoKnowledgeBase.from_directory(kb_root)
    return _cached_demo_kb


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text

    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text

    frontmatter, content = parts
    metadata: dict[str, Any] = {}
    for line in frontmatter.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = _coerce_value(value)
    return metadata, content


def _title_from_content(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _flatten_metadata(metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in metadata.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return values


def _build_excerpt(content: str, overlap: set[str]) -> str:
    for paragraph in content.split("\n\n"):
        lowered = paragraph.lower()
        if any(token in lowered for token in overlap):
            return " ".join(paragraph.split())[:260]
    return " ".join(content.split())[:260]
