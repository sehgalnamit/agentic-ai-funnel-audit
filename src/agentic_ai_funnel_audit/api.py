from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .pipeline import AuditPipeline
from .storage import AuditStore

app = FastAPI(title="Agentic AI Funnel Audit")

pipeline = AuditPipeline()
audit_store = AuditStore()


class IdeaRequest(BaseModel):
    id: str
    description: str
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
    service_telemetry: dict[str, Any] | None = None
    incident_history: dict[str, Any] | None = None
    backlog_health: dict[str, Any] | None = None
    architecture_metadata: dict[str, Any] | None = None


class AuditPayload(BaseModel):
    idea: IdeaRequest
    context: IdeaContext | None = Field(default=None)


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
      </body>
    </html>
    """


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
