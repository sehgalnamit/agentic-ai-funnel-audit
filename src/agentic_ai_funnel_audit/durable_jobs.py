from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
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
    """JSON-backed local development job state store."""

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


class FirestoreDurableJobStore:
    """Firestore-backed durable job state shared by API and worker instances."""

    def __init__(self, collection: str = "agentic_audit_jobs") -> None:
        try:
            from google.cloud import firestore  # type: ignore
        except Exception as exc:
            raise RuntimeError("google-cloud-firestore is required for Firestore job storage.") from exc
        self._client = firestore.Client()
        self._collection = self._client.collection(collection)

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
        snapshot = self._collection.document(job_id).get()
        return DurableJob(**snapshot.to_dict()) if snapshot.exists else None

    def mark_queued(self, job_id: str, message_id: str) -> DurableJob | None:
        return self._update(job_id, status="queued", message_id=message_id)

    def mark_running(self, job_id: str) -> DurableJob | None:
        return self._update(job_id, status="running")

    def mark_completed(self, job_id: str, results: list[dict[str, Any]]) -> DurableJob | None:
        return self._update(job_id, status="completed", results=results)

    def mark_failed(self, job_id: str, error: str) -> DurableJob | None:
        return self._update(job_id, status="failed", error=error)

    def _update(self, job_id: str, **changes: Any) -> DurableJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = _utc_now()
        self._write(job)
        return job

    def _write(self, job: DurableJob) -> None:
        self._collection.document(job.job_id).set(job.to_dict())


def create_durable_job_store(root: Path) -> DurableJobStore | FirestoreDurableJobStore:
    backend = os.getenv("AGENTIC_JOB_STORE_BACKEND", "file").strip().lower()
    if backend == "firestore":
        collection = os.getenv("AGENTIC_FIRESTORE_JOB_COLLECTION", "agentic_audit_jobs")
        return FirestoreDurableJobStore(collection)
    if backend != "file":
        raise ValueError("AGENTIC_JOB_STORE_BACKEND must be 'file' or 'firestore'.")
    return DurableJobStore(root)
