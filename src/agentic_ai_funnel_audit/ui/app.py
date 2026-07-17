import os
import sys
import uuid
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

# Make the package importable when running from the repo root
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentic_ai_funnel_audit.storage import AuditStore
from agentic_ai_funnel_audit.pipeline import AuditPipeline

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")
store = AuditStore()
pipeline = AuditPipeline()


def _to_int(value, default):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


@app.route("/")
def index():
    return redirect(url_for("intake"))


@app.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        idea_id = request.form.get("idea_id") or str(uuid.uuid4())
        dependencies_count = _to_int(request.form.get("dependencies_count"), 1)
        data_maturity = _to_int(request.form.get("data_maturity"), 3)
        workflow_overlap = _to_int(request.form.get("workflow_overlap"), 0)
        trend_score = _to_int(request.form.get("trend_score"), 3)
        competitor_signal = _to_int(request.form.get("competitor_signal"), 3)
        market_risk = _to_int(request.form.get("market_risk"), 3)
        strategic_fit = _to_int(request.form.get("strategic_fit"), 3)

        payload = {
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "owner": request.form.get("owner"),
            "estimated_benefit": request.form.get("estimated_benefit"),
            "dependencies_count": dependencies_count,
            "data_maturity": data_maturity,
            "workflow_overlap": workflow_overlap,
            "trend_score": trend_score,
            "competitor_signal": competitor_signal,
            "market_risk": market_risk,
            "strategic_fit": strategic_fit,
        }

        description = payload["description"] or ""
        contains_sensitive_concepts = bool(
            request.form.get("contains_sensitive_concepts")
            or any(token in description.lower() for token in ["api key", "password", "private key", "confidential"])
        )

        # Build an idea dict the pipeline understands
        idea = {
            "id": idea_id,
            "description": payload["description"] or payload["title"],
            "dependencies": [f"dep-{i+1}" for i in range(max(0, dependencies_count))],
            "workflow_overlap": workflow_overlap,
            "trend_score": trend_score,
            "market_risk": market_risk,
            "strategic_fit": strategic_fit,
            "contains_sensitive_concepts": contains_sensitive_concepts,
        }
        context = {
            "data_maturity": data_maturity,
            "competitor_signal": competitor_signal,
            "service_telemetry": {
                "uptime": 99.8 if data_maturity >= 3 else 98.5,
                "slo_breach_count": 0 if workflow_overlap <= 1 else 2,
            },
            "incident_history": {"severity": 2 if workflow_overlap <= 1 else 4},
            "backlog_health": {"delivery_velocity": 4 if data_maturity >= 3 else 2},
            "architecture_metadata": {"legacy_systems": max(1, dependencies_count // 2)},
        }
        try:
            result = pipeline.run(idea, context)
            audit_result = {
                "final_score": result.final_score,
                "pass_gate": result.pass_gate,
                "iso_scores": result.iso_scores,
                "evaluations": [
                    {"name": e.name, "score": e.score, "rationale": e.rationale}
                    for e in result.evaluations
                ],
                "deliberation": {
                    "name": result.deliberation.name,
                    "score": result.deliberation.score,
                    "rationale": result.deliberation.rationale,
                },
                "safety": {
                    "name": result.safety.name,
                    "score": result.safety.score,
                    "rationale": result.safety.rationale,
                },
                "governance": result.governance,
                "execution_mode": "Local root agent + subagents",
                "model_enabled": pipeline.model_evaluator.is_enabled(),
                "model_name": pipeline.model_evaluator.model_name,
            }
        except Exception as exc:
            audit_result = {"error": str(exc)}
        entry = store.save(idea_id, payload, audit_result=audit_result)
        flash(f"Saved intake: {entry.idea_id}")
        return redirect(url_for("entry_detail", idea_id=entry.idea_id))
    return render_template("intake.html")


@app.route("/dashboard")
def dashboard():
    entries = store.list()
    return render_template("dashboard.html", entries=entries)


@app.route("/entry/<idea_id>", methods=["GET"])
def entry_detail(idea_id):
    entry = store.get(idea_id)
    if not entry:
        flash("Entry not found", "danger")
        return redirect(url_for("dashboard"))
    return render_template("detail.html", entry=entry)


@app.route("/entry/<idea_id>/override", methods=["POST"])
def entry_override(idea_id):
    action = request.form.get("action")
    comment = request.form.get("comment")
    override_payload = {"action": action, "comment": comment, "by": request.form.get("user")}
    entry = store.override(idea_id, override_payload)
    if not entry:
        flash("Failed to override: entry not found", "danger")
    else:
        flash(f"Set override for {idea_id}: {action}")
    return redirect(url_for("entry_detail", idea_id=idea_id))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
