from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .pipeline import AuditPipeline
from .storage import AuditStore
from .connectors import OperationalDataFetcher
from .outcomes import OutcomeStore, OutcomeRecord, FeedbackLoopCalibrator

app = FastAPI(title="Agentic AI Funnel Audit")

pipeline = AuditPipeline()
audit_store = AuditStore()
data_fetcher = OperationalDataFetcher()
outcome_store = OutcomeStore()
calibrator = FeedbackLoopCalibrator(outcome_store)


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


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/audit")
def audit_idea(payload: AuditPayload):
    idea = payload.idea.model_dump()
    context_data = payload.context.model_dump() if payload.context else {}
    result = pipeline.run(idea, context_data)
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
