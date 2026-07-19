import os
import sys
import uuid
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

# Make the package importable when running from the repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentic_ai_funnel_audit.storage import AuditStore
from agentic_ai_funnel_audit.knowledge_base import load_demo_knowledge_base
from agentic_ai_funnel_audit.pipeline import AuditPipeline

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")
store = AuditStore()
pipeline = AuditPipeline()
demo_kb = load_demo_knowledge_base()


def _csv_list(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@app.route("/")
def index():
    return redirect(url_for("intake"))


@app.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        idea_id = request.form.get("idea_id") or str(uuid.uuid4())
        title = request.form.get("title")
        problem_statement = request.form.get("problem_statement")
        business_outcome = request.form.get("business_outcome")
        sponsor = request.form.get("sponsor")
        target_users = request.form.get("target_users")
        kpi_target = request.form.get("estimated_benefit")
        current_process = request.form.get("current_process")
        systems_involved = _csv_list(request.form.get("systems_involved"))
        required_data_sources = _csv_list(request.form.get("required_data_sources"))
        known_dependencies = _csv_list(request.form.get("known_dependencies")) or systems_involved
        geographic_scope = request.form.get("geographic_scope")
        delivery_timeline = request.form.get("delivery_timeline")
        ai_pattern = request.form.get("ai_pattern")
        human_review = request.form.get("human_review")
        known_risks = request.form.get("known_risks")

        workflow_overlap = min(3, max(0, len(systems_involved) - 1))
        telemetry_uptime = 99.8 if len(systems_involved) <= 2 else 98.9
        slo_breaches = 0 if len(systems_involved) <= 2 else 1
        delivery_velocity = 4 if len(required_data_sources) <= 2 else 2
        legacy_systems = sum(1 for item in systems_involved if "legacy" in item.lower() or "support" in item.lower())

        payload = {
            "title": title,
            "problem_statement": problem_statement,
            "business_outcome": business_outcome,
            "sponsor": sponsor,
            "target_users": target_users,
            "estimated_benefit": kpi_target,
            "current_process": current_process,
            "systems_involved": systems_involved,
            "required_data_sources": required_data_sources,
            "known_dependencies": known_dependencies,
            "geographic_scope": geographic_scope,
            "delivery_timeline": delivery_timeline,
            "ai_pattern": ai_pattern,
            "human_review": human_review,
            "known_risks": known_risks,
        }

        description = "\n".join(
            part for part in [problem_statement, business_outcome, current_process, known_risks] if part
        ) or title or ""
        contains_sensitive_concepts = bool(
            request.form.get("contains_sensitive_concepts")
            or any(token in description.lower() for token in ["api key", "password", "private key", "confidential"])
        )

        idea = {
            "id": idea_id,
            "title": title,
            "description": description,
            "business_outcome": business_outcome,
            "target_users": target_users,
            "current_process": current_process,
            "systems_involved": systems_involved,
            "required_data_sources": required_data_sources,
            "dependencies": known_dependencies,
            "workflow_overlap": workflow_overlap,
            "kpi_target": kpi_target,
            "sponsor": sponsor,
            "contains_sensitive_concepts": contains_sensitive_concepts,
        }
        context = {
            "geography": geographic_scope,
            "service_telemetry": {
                "uptime": telemetry_uptime,
                "slo_breach_count": slo_breaches,
            },
            "incident_history": {"severity": 2 if workflow_overlap <= 1 else 3},
            "backlog_health": {"delivery_velocity": delivery_velocity},
            "architecture_metadata": {"legacy_systems": legacy_systems, "integration_count": len(systems_involved)},
            "knowledge_base": demo_kb,
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
                "report": result.report,
                "execution_mode": "Local root agent + KB-backed subagents",
                "model_enabled": pipeline.model_evaluator.is_enabled(),
                "model_name": pipeline.model_evaluator.model_name,
            }
        except Exception as exc:
            audit_result = {"error": str(exc)}
        entry = store.save(idea_id, payload, audit_result=audit_result)
        flash(f"Saved intake: {entry.idea_id}")
        return redirect(url_for("entry_detail", idea_id=entry.idea_id))
    return render_template("intake.html")


@app.route("/knowledge-base")
def knowledge_base():
    template_path = REPO_ROOT / "demo_kb" / "templates" / "idea-intake-template.md"
    intake_template = template_path.read_text(encoding="utf-8")
    return render_template(
        "knowledge_base.html",
        grouped_documents=demo_kb.grouped_documents(),
        intake_template=intake_template,
    )


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
