from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .durable_jobs import create_durable_job_store
from .knowledge_base import load_knowledge_base
from .pipeline import AuditPipeline
from .storage import AuditStore


def run_pubsub_worker() -> None:
    subscription_path = os.getenv("AGENTIC_PUBSUB_SUBSCRIPTION", "").strip()
    if not subscription_path:
        raise RuntimeError("AGENTIC_PUBSUB_SUBSCRIPTION is required. Expected projects/<project>/subscriptions/<name>")

    try:
        from google.cloud import pubsub_v1  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"google-cloud-pubsub is required for worker mode. Error: {exc}") from exc

    pipeline = AuditPipeline()
    audit_store = AuditStore()
    jobs = create_durable_job_store(Path(os.getenv("AGENTIC_JOB_STORE_DIR", "runtime_jobs")))

    subscriber = pubsub_v1.SubscriberClient()

    def callback(message: Any) -> None:
        try:
            envelope = json.loads(message.data.decode("utf-8"))
            job_id = str(envelope.get("job_id") or "").strip()
            if not job_id:
                raise ValueError("missing job_id in envelope")

            jobs.mark_running(job_id)
            mode = str(envelope.get("knowledge_base_mode") or os.getenv("AGENTIC_KB_MODE", "demo")).strip().lower()
            context = dict(envelope.get("context") or {})
            context["knowledge_base"] = load_knowledge_base(mode)
            idea_payloads = envelope.get("ideas") or []
            results = pipeline.run_batch(idea_payloads, context)

            serialized: list[dict[str, Any]] = []
            for result, idea in zip(results, idea_payloads):
                row = {
                    "idea_id": result.idea_id,
                    "final_score": result.final_score,
                    "pass_gate": result.pass_gate,
                    "iso_scores": result.iso_scores,
                    "report": result.report,
                }
                audit_store.save(
                    idea_id=result.idea_id,
                    payload={
                        "idea": idea,
                        "context": {k: v for k, v in context.items() if k != "knowledge_base"},
                        "result": {
                            "final_score": result.final_score,
                            "pass_gate": result.pass_gate,
                            "iso_scores": result.iso_scores,
                            "report": result.report,
                            "artifact": result.artifact,
                        },
                    },
                )
                serialized.append(row)

            jobs.mark_completed(job_id, serialized)
            message.ack()
        except Exception as exc:
            try:
                envelope = json.loads(message.data.decode("utf-8"))
                job_id = str(envelope.get("job_id") or "").strip()
                if job_id:
                    jobs.mark_failed(job_id, str(exc))
            finally:
                message.nack()

    streaming_pull = subscriber.subscribe(subscription_path, callback=callback)
    print(f"Pub/Sub worker listening on {subscription_path}")
    streaming_pull.result()


if __name__ == "__main__":
    run_pubsub_worker()
