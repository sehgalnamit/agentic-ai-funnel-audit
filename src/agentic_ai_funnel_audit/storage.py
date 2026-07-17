import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AuditEntry:
    idea_id: str
    payload: dict[str, Any]
    created_at: str
    override: dict[str, Any] | None = None
    audit_result: dict[str, Any] | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_summary(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "created_at": self.created_at,
            "override": self.override,
        }


class AuditStore:
    def __init__(self):
        self._entries: dict[str, AuditEntry] = {}

    def save(self, idea_id: str, payload: dict[str, Any], audit_result: dict[str, Any] | None = None) -> AuditEntry:
        entry = AuditEntry(
            idea_id=idea_id,
            payload=payload,
            created_at=datetime.now(timezone.utc).isoformat(),
            audit_result=audit_result,
        )
        self._entries[idea_id] = entry
        return entry

    def get(self, idea_id: str) -> AuditEntry | None:
        return self._entries.get(idea_id)

    def list(self) -> list[AuditEntry]:
        return list(self._entries.values())

    def override(self, idea_id: str, override_payload: dict[str, Any]) -> AuditEntry | None:
        entry = self._entries.get(idea_id)
        if not entry:
            return None
        entry.override = override_payload
        return entry
