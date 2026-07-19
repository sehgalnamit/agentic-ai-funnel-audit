from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DurableJob:
    job_id: str
    status: str
    backend: str
    created_at: str
    updated_at: str
    count: int
    message_id: str | None = None
    results: list[dict[str, Any]] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "backend": self.backend,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "count": self.count,
            "message_id": self.message_id,
            "results": self.results or [],
            "error": self.error,
        }


class DurableJobStore:
    """Simple JSON-backed job state store for pub/sub workers.

    This preserves async job status across process restarts without requiring
    a database in local or early production environments.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create_submitted(self, count: int, backend: str = "pubsub") -> DurableJob:
        timestamp = _utc_now()
        job = DurableJob(
            job_id=str(uuid.uuid4()),
            status="submitted",
            backend=backend,
            created_at=timestamp,
            updated_at=timestamp,
            count=count,
        )
        self._write(job)
        return job

    def get(self, job_id: str) -> DurableJob | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return DurableJob(**payload)

    def mark_queued(self, job_id: str, message_id: str) -> DurableJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = "queued"
        job.message_id = message_id
        job.updated_at = _utc_now()
        self._write(job)
        return job

    def mark_running(self, job_id: str) -> DurableJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = "running"
        job.updated_at = _utc_now()
        self._write(job)
        return job

    def mark_completed(self, job_id: str, results: list[dict[str, Any]]) -> DurableJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = "completed"
        job.results = results
        job.updated_at = _utc_now()
        self._write(job)
        return job

    def mark_failed(self, job_id: str, error: str) -> DurableJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = "failed"
        job.error = error
        job.updated_at = _utc_now()
        self._write(job)
        return job

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _write(self, job: DurableJob) -> None:
        with self._lock:
            self._path(job.job_id).write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
