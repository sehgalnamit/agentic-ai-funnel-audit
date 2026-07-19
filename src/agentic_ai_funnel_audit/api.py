from typing import Any
import asyncio
import base64
import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .pipeline import AuditPipeline
from .batch_jobs import BatchAuditJobManager
from .storage import AuditStore
from .connectors import OperationalDataFetcher
from .knowledge_base import load_knowledge_base
from .knowledge_ingestion import KnowledgeIngestionJob, KnowledgeSyncPlanner, SnapshotKnowledgeWriter
from .source_adapters import build_default_adapters
from .outcomes import OutcomeStore, OutcomeRecord, FeedbackLoopCalibrator
from .durable_jobs import create_durable_job_store
from .tool_gateway import ToolDefinition, ToolGateway, ToolGatewayError
from .observability import observability

app = FastAPI(title="Agentic AI Funnel Audit")

pipeline = AuditPipeline()
audit_store = AuditStore()
data_fetcher = OperationalDataFetcher()
outcome_store = OutcomeStore()
calibrator = FeedbackLoopCalibrator(outcome_store)
sync_planner = KnowledgeSyncPlanner()
snapshot_writer = SnapshotKnowledgeWriter(root=(Path(__file__).resolve().parents[2] / "knowledge_snapshots"))
batch_job_manager = BatchAuditJobManager(pipeline=pipeline, audit_store=audit_store)
durable_job_store = create_durable_job_store(Path(os.getenv("AGENTIC_JOB_STORE_DIR", "runtime_jobs")))
source_adapters = build_default_adapters()
tool_gateway = ToolGateway()


class IdeaRequest(BaseModel):
    id: str
    title: str | None = None
    description: str
    business_outcome: str | None = None
    target_users: list[str] = []
    current_process: str | None = None
    systems_involved: list[str] = []
    required_data_sources: list[str] = []
    kpi_target: str | None = None
    sponsor: str | None = None
    dependencies: list[str] = []
    workflow_overlap: int = 0
    trend_score: int = 3
    market_risk: int = 2
    strategic_fit: int = 3
    contains_sensitive_concepts: bool = False


class IdeaContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    data_maturity: int = 3
    competitor_signal: int = 3
    geography: str | None = None
    industry: str | None = None
    service_telemetry: dict[str, Any] | None = None
    incident_history: dict[str, Any] | None = None
    backlog_health: dict[str, Any] | None = None
    architecture_metadata: dict[str, Any] | None = None


class AuditPayload(BaseModel):
    idea: IdeaRequest
    context: IdeaContext | None = Field(default=None)
    service_id: str | None = Field(default=None)
    team_id: str | None = Field(default=None)
    knowledge_base_mode: str | None = Field(default=None)


class BatchAuditPayload(BaseModel):
    ideas: list[IdeaRequest]
    context: IdeaContext | None = Field(default=None)
    knowledge_base_mode: str | None = Field(default=None)
    async_backend: str | None = Field(default=None)


class KnowledgeIngestionRequest(BaseModel):
    domain: str
    owner: str
    source_system: str
    refresh_mode: str = "async"
    refresh_cadence: str = "daily"
    content_type: str = "markdown"
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutcomeRequest(BaseModel):
    idea_id: str
    outcome_status: str
    implementation_duration_weeks: int
    actual_delivery_cost: float
    actual_team_velocity_impact: int
    business_value_realized: int
    risk_incidents_count: int
    technical_debt_added: int
    process_improvements: list[str] = []
    lessons_learned: str = ""


class KnowledgeSyncRequest(BaseModel):
    source_types: list[str] = Field(default_factory=list)


class ToolInvocationRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    roles: list[str] = Field(default_factory=list)


def _tool_search_knowledge(arguments: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    kb = _resolve_knowledge_base(arguments.get("knowledge_base_mode"))
    return {
        "hits": [
            hit.to_dict()
            for hit in kb.search(
                domain=str(arguments["domain"]),
                query=str(arguments["query"]),
                limit=min(10, max(1, int(arguments.get("limit", 3)))),
                access_context=identity,
            )
        ]
    }


def _tool_get_audit(arguments: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    _ = identity
    entry = audit_store.get(str(arguments["idea_id"]))
    if not entry:
        raise ToolGatewayError("Audit entry not found.", status_code=404)
    return {"idea_id": entry.idea_id, "created_at": entry.created_at, "payload": entry.payload}


tool_gateway.register(
    ToolDefinition(
        name="knowledge.search",
        allowed_roles={"auditor", "retriever", "reviewer"},
        required_fields={"domain", "query"},
        handler=_tool_search_knowledge,
    )
)
tool_gateway.register(
    ToolDefinition(
        name="audit.get",
        allowed_roles={"auditor", "reviewer"},
        required_fields={"idea_id"},
        handler=_tool_get_audit,
    )
)


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/mcp/tools")
def list_mcp_tools(x_agent_roles: str = Header(default="")):
    roles = [role.strip() for role in x_agent_roles.split(",") if role.strip()]
    return {"protocol": "mcp-tool-gateway", "tools": tool_gateway.describe(roles)}


@app.post("/mcp/tools/{tool_name}")
def invoke_mcp_tool(
    tool_name: str,
    payload: ToolInvocationRequest,
    x_agent_roles: str = Header(default=""),
    x_tool_gateway_token: str | None = Header(default=None),
):
    header_roles = [role.strip() for role in x_agent_roles.split(",") if role.strip()]
    identity = {"roles": header_roles or payload.roles}
    try:
        result = tool_gateway.execute(tool_name, payload.arguments, identity, x_tool_gateway_token)
    except ToolGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"tool": tool_name, "result": result}


@app.post("/audit")
def audit_idea(payload: AuditPayload):
    with observability.timed_span("audit.api.route", {"route": "/audit"}):
        idea = payload.idea.model_dump()
        context_data = payload.context.model_dump() if payload.context else {}
        runtime_context = dict(context_data)
        runtime_context["knowledge_base"] = _resolve_knowledge_base(payload.knowledge_base_mode)
        result = pipeline.run(idea, runtime_context)
        audit_store.save(idea_id=result.idea_id, payload={
            "idea": idea,
            "context": context_data,
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
        })

        return {
            "idea_id": result.idea_id,
            "final_score": result.final_score,
            "pass_gate": result.pass_gate,
            "iso_scores": result.iso_scores,
            "governance": result.governance,
            "policy": result.policy,
            "feedback_adjustment": result.feedback_adjustment,
            "report": result.report,
            "artifact": result.artifact,
            "deliberation": {
                "name": result.deliberation.name,
                "score": result.deliberation.score,
                "rationale": result.deliberation.rationale,
            },
        }


@app.post("/audit/batch")
def audit_batch(payload: BatchAuditPayload):
    with observability.timed_span("audit.api.route", {"route": "/audit/batch", "count": len(payload.ideas)}):
        shared_context = payload.context.model_dump() if payload.context else {}
        shared_context["knowledge_base"] = _resolve_knowledge_base(payload.knowledge_base_mode)
        ideas = [idea.model_dump() for idea in payload.ideas]
        results = pipeline.run_batch(ideas, shared_context)

        output = []
        for result, idea in zip(results, ideas):
            audit_store.save(idea_id=result.idea_id, payload={
                "idea": idea,
                "context": {key: value for key, value in shared_context.items() if key != "knowledge_base"},
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
            })
            output.append({
                "idea_id": result.idea_id,
                "final_score": result.final_score,
                "pass_gate": result.pass_gate,
                "iso_scores": result.iso_scores,
                "report": result.report,
            })

        return {
            "count": len(output),
            "results": output,
        }


@app.post("/audit/batch/async")
def audit_batch_async(payload: BatchAuditPayload):
    with observability.timed_span("audit.api.route", {"route": "/audit/batch/async", "count": len(payload.ideas)}):
        shared_context = payload.context.model_dump() if payload.context else {}
        backend = _resolve_async_backend(payload.async_backend)

        if backend == "pubsub":
            durable_job = durable_job_store.create_submitted(count=len(payload.ideas), backend="pubsub")
            envelope = {
                "job_id": durable_job.job_id,
                "ideas": [idea.model_dump() for idea in payload.ideas],
                "context": shared_context,
                "knowledge_base_mode": payload.knowledge_base_mode or os.getenv("AGENTIC_KB_MODE", "demo"),
            }
            message_id = _publish_pubsub(envelope)
            durable_job_store.mark_queued(durable_job.job_id, message_id)
            return {
                "job_id": durable_job.job_id,
                "status": "submitted",
                "backend": "pubsub",
                "message_id": message_id,
                "count": len(payload.ideas),
            }

        shared_context["knowledge_base"] = _resolve_knowledge_base(payload.knowledge_base_mode)
        ideas = [idea.model_dump() for idea in payload.ideas]
        job = batch_job_manager.submit(ideas, shared_context)
        response = job.to_dict()
        response["backend"] = "local"
        return response


@app.post("/events/pubsub")
def consume_pubsub_batch_event(payload: dict[str, Any]):
    """Cloud Run Pub/Sub push target for durable batch execution."""
    try:
        encoded = payload["message"]["data"]
        envelope = json.loads(base64.b64decode(encoded).decode("utf-8"))
        job_id = str(envelope["job_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub job envelope.") from exc

    durable_job = durable_job_store.get(job_id)
    if durable_job is None:
        raise HTTPException(status_code=404, detail="Durable job was not found.")
    if durable_job.status == "completed":
        return {"status": "already_completed", "job_id": job_id}

    try:
        durable_job_store.mark_running(job_id)
        context = dict(envelope.get("context") or {})
        context["knowledge_base"] = _resolve_knowledge_base(envelope.get("knowledge_base_mode"))
        ideas = list(envelope.get("ideas") or [])
        results = pipeline.run_batch(ideas, context)
        output = []
        for result, idea in zip(results, ideas):
            audit_store.save(
                idea_id=result.idea_id,
                payload={
                    "idea": idea,
                    "context": {key: value for key, value in context.items() if key != "knowledge_base"},
                    "result": {
                        "final_score": result.final_score,
                        "pass_gate": result.pass_gate,
                        "iso_scores": result.iso_scores,
                        "report": result.report,
                        "artifact": result.artifact,
                    },
                },
            )
            output.append({"idea_id": result.idea_id, "final_score": result.final_score, "pass_gate": result.pass_gate})
        durable_job_store.mark_completed(job_id, output)
        return {"status": "completed", "job_id": job_id}
    except Exception as exc:
        durable_job_store.mark_failed(job_id, str(exc))
        raise HTTPException(status_code=500, detail="Pub/Sub job processing failed.") from exc


@app.get("/audit/jobs/{job_id}")
def get_audit_job(job_id: str):
    job = batch_job_manager.get(job_id)
    if job:
        return job.to_dict()

    durable = durable_job_store.get(job_id)
    if durable:
        return durable.to_dict()

    if not job:
        raise HTTPException(status_code=404, detail="Audit job not found.")
    return job.to_dict()


@app.get("/knowledge-base/status")
def get_knowledge_base_status():
    kb = _resolve_knowledge_base(None)
    return {
        "domains": [status.to_dict() for status in kb.domain_statuses()],
        "mode": os.getenv("AGENTIC_KB_MODE", "demo").strip().lower(),
        "production_note": (
            "In production, each domain should be refreshed asynchronously from authoritative company systems, "
            "not edited manually in app storage."
        ),
        "ingestion_contracts": sync_planner.describe(),
    }


@app.post("/knowledge-base/ingest")
def ingest_knowledge_snapshot(payload: KnowledgeIngestionRequest):
    job = KnowledgeIngestionJob(
        domain=payload.domain,
        owner=payload.owner,
        source_system=payload.source_system,
        refresh_mode=payload.refresh_mode,
        refresh_cadence=payload.refresh_cadence,
        content_type=payload.content_type,
        title=payload.title,
        content=payload.content,
        metadata=payload.metadata,
    )
    path = asyncio.run(snapshot_writer.ingest(job))
    return {
        "status": "accepted",
        "path": str(path),
        "domain": payload.domain,
        "title": payload.title,
        "refresh_mode": payload.refresh_mode,
    }


@app.post("/knowledge-base/sync")
def sync_knowledge_from_sources(payload: KnowledgeSyncRequest):
    requested = {item.strip().lower() for item in payload.source_types if item.strip()}
    accepted: list[dict[str, Any]] = []

    for adapter in source_adapters:
        if requested and adapter.source_type not in requested:
            continue
        jobs = adapter.build_jobs()
        for job in jobs:
            path = asyncio.run(snapshot_writer.ingest(job))
            accepted.append(
                {
                    "source_type": adapter.source_type,
                    "domain": job.domain,
                    "title": job.title,
                    "path": str(path),
                }
            )

    return {
        "status": "accepted",
        "ingested_count": len(accepted),
        "records": accepted,
    }


def _resolve_knowledge_base(mode: str | None):
    requested_mode = (mode or os.getenv("AGENTIC_KB_MODE", "demo")).strip().lower()
    return load_knowledge_base(requested_mode)


def _resolve_async_backend(backend: str | None) -> str:
    resolved = (backend or os.getenv("AGENTIC_ASYNC_BACKEND", "local")).strip().lower()
    if resolved not in {"local", "pubsub"}:
        raise HTTPException(status_code=400, detail="async backend must be 'local' or 'pubsub'.")
    return resolved


def _publish_pubsub(envelope: dict[str, Any]) -> str:
    topic_path = os.getenv("AGENTIC_PUBSUB_TOPIC", "").strip()
    if not topic_path:
        raise HTTPException(
            status_code=400,
            detail="AGENTIC_PUBSUB_TOPIC is required for pubsub backend. Expected: projects/<project>/topics/<topic>",
        )
    try:
        from google.cloud import pubsub_v1  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"google-cloud-pubsub is required for pubsub backend. Install dependency first. Error: {exc}",
        )

    publisher = pubsub_v1.PublisherClient()
    payload = json.dumps(envelope).encode("utf-8")
    future = publisher.publish(topic_path, payload)
    return str(future.result(timeout=10))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    entries = audit_store.list()
    rows = "".join(
        f"<li><strong>{entry.idea_id}</strong> @ {entry.created_at} - override={entry.override is not None}</li>"
        for entry in entries
    )
    return f"""
    <html>
      <head><title>CTAO Innovation Audit Dashboard</title></head>
      <body>
        <h1>CTAO Innovation Audit Dashboard</h1>
        <p>This dashboard shows audit review history and override status.</p>
        <ul>{rows}</ul>
        <p>Use the /audit endpoint to submit an idea and /audit/{'{idea_id}'}/override to apply an executive override.</p>
        <p>Use /audits to fetch all saved audit entries and /audit/{'{idea_id}'}/artifact to download the audit artifact.</p>
      </body>
    </html>
    """


@app.get("/audits")
def list_audits():
    return [entry.to_summary() for entry in audit_store.list()]


@app.get("/audit/{idea_id}")
def get_audit(idea_id: str):
    entry = audit_store.get(idea_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit entry not found.")
    return {
        "idea_id": entry.idea_id,
        "created_at": entry.created_at,
        "override": entry.override,
        "payload": entry.payload,
    }


@app.get("/audit/{idea_id}/artifact")
def get_audit_artifact(idea_id: str):
    entry = audit_store.get(idea_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit entry not found.")
    artifact = entry.payload.get("result", {}).get("artifact")
    if artifact is None:
        raise HTTPException(status_code=404, detail="Audit artifact not available.")
    return artifact


class AuditOverrideRequest(BaseModel):
    override_reason: str
    approved: bool
    reviewer: str


@app.post("/audit/{idea_id}/override")
def override_audit(idea_id: str, override: AuditOverrideRequest):
    entry = audit_store.get(idea_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit entry not found.")

    updated = audit_store.override(idea_id, override_payload=override.model_dump())
    return {
        "idea_id": updated.idea_id,
        "override": updated.override,
        "created_at": updated.created_at,
    }


@app.get("/audit/{idea_id}/enrich")
def enrich_context(idea_id: str, service_id: str | None = None, team_id: str | None = None):
    """Fetch and enrich context from operational data sources."""
    if not service_id or not team_id:
        raise HTTPException(status_code=400, detail="service_id and team_id are required.")

    enriched = data_fetcher.fetch_all_context(service_id, team_id)
    return {
        "idea_id": idea_id,
        "enriched_context": enriched,
    }


@app.post("/outcomes")
def record_outcome(outcome_payload: OutcomeRequest):
    """Record an outcome for a completed idea."""
    outcome = OutcomeRecord(
        idea_id=outcome_payload.idea_id,
        outcome_status=outcome_payload.outcome_status,
        implementation_duration_weeks=outcome_payload.implementation_duration_weeks,
        actual_delivery_cost=outcome_payload.actual_delivery_cost,
        actual_team_velocity_impact=outcome_payload.actual_team_velocity_impact,
        business_value_realized=outcome_payload.business_value_realized,
        risk_incidents_count=outcome_payload.risk_incidents_count,
        technical_debt_added=outcome_payload.technical_debt_added,
        process_improvements=outcome_payload.process_improvements,
        lessons_learned=outcome_payload.lessons_learned,
    )
    recorded = outcome_store.record_outcome(outcome_payload.idea_id, outcome)
    return {
        "idea_id": recorded.idea_id,
        "outcome_status": recorded.outcome_status,
        "feedback_signal": recorded.to_feedback_signal(),
    }


@app.get("/outcomes")
def list_outcomes():
    """List all recorded outcomes."""
    return [
        {
            "idea_id": o.idea_id,
            "outcome_status": o.outcome_status,
            "created_at": o.created_at,
            "feedback_signal": o.to_feedback_signal(),
        }
        for o in outcome_store.list_outcomes()
    ]


@app.get("/outcomes/{idea_id}")
def get_outcome(idea_id: str):
    """Get outcome for a specific idea."""
    outcome = outcome_store.get_outcome(idea_id)
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not found.")
    return {
        "idea_id": outcome.idea_id,
        "outcome_status": outcome.outcome_status,
        "created_at": outcome.created_at,
        "feedback_signal": outcome.to_feedback_signal(),
    }


@app.get("/calibration")
def get_calibration_factors():
    """Get feedback loop calibration factors."""
    factors = outcome_store.compute_calibration_factors()
    return {
        "calibration_factors": factors,
        "total_outcomes_recorded": len(outcome_store.list_outcomes()),
        "feedback_history_size": len(outcome_store.get_feedback_history()),
    }
