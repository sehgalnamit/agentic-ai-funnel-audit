from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Queue, Empty
from threading import Lock, Thread
import traceback
from typing import Any
import uuid

from .pipeline import AuditPipeline
from .storage import AuditStore


@dataclass
class BatchAuditJob:
    id: str
    status: str
    created_at: str
    updated_at: str
    ideas: list[dict[str, Any]]
    context: dict[str, Any]
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    backend: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "backend": self.backend,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "results": self.results,
            "error": self.error,
            "count": len(self.ideas),
        }


class BatchAuditJobManager:
    def __init__(self, pipeline: AuditPipeline, audit_store: AuditStore):
        self.pipeline = pipeline
        self.audit_store = audit_store
        self._jobs: dict[str, BatchAuditJob] = {}
        self._queue: Queue[str] = Queue()
        self._lock = Lock()
        self._worker = Thread(target=self._work_loop, daemon=True, name="audit-batch-worker")
        self._worker.start()

    def submit(self, ideas: list[dict[str, Any]], context: dict[str, Any]) -> BatchAuditJob:
        timestamp = datetime.now(timezone.utc).isoformat()
        job = BatchAuditJob(
            id=str(uuid.uuid4()),
            status="submitted",
            created_at=timestamp,
            updated_at=timestamp,
            ideas=ideas,
            context=context,
        )
        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> BatchAuditJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _work_loop(self) -> None:
        while True:
            try:
                job_id = self._queue.get(timeout=0.5)
            except Empty:
                continue
            self._run_job(job_id)
            self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        self._update(job, status="running")
        try:
            results = self.pipeline.run_batch(job.ideas, job.context)
            payloads: list[dict[str, Any]] = []
            for result, idea in zip(results, job.ideas):
                clean_context = {key: value for key, value in job.context.items() if key != "knowledge_base"}
                self.audit_store.save(
                    idea_id=result.idea_id,
                    payload={
                        "idea": idea,
                        "context": clean_context,
                        "result": {
                            "final_score": result.final_score,
                            "pass_gate": result.pass_gate,
                            "iso_scores": result.iso_scores,
                            "governance": result.governance,
                            "policy": result.policy,
                            "feedback_adjustment": result.feedback_adjustment,
                            "report": result.report,
                            "artifact": result.artifact,
                        },
                    },
                )
                payloads.append({
                    "idea_id": result.idea_id,
                    "final_score": result.final_score,
                    "pass_gate": result.pass_gate,
                    "iso_scores": result.iso_scores,
                    "report": result.report,
                })
            self._update(job, status="completed", results=payloads)
        except Exception:
            self._update(job, status="failed", error=traceback.format_exc())

    def _update(self, job: BatchAuditJob, status: str, results: list[dict[str, Any]] | None = None, error: str | None = None) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            job.status = status
            job.updated_at = timestamp
            if results is not None:
                job.results = results
            if error is not None:
                job.error = error
