import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_ai_funnel_audit.pipeline import AuditPipeline


def test_audit_pipeline_passes_gate_for_aligned_idea():
    pipeline = AuditPipeline()

    idea = {
        "id": "idea-001",
        "dependencies": ["data-platform"],
        "workflow_overlap": 0,
        "trend_score": 4,
        "market_risk": 1,
        "strategic_fit": 4,
    }
    context = {
        "data_maturity": 4,
        "competitor_signal": 3,
    }

    result = pipeline.run(idea, context)

    assert result.idea_id == "idea-001"
    assert result.final_score >= 3
    assert result.iso_scores["Strategic Alignment"] == 4
    assert result.iso_scores["Constraint Fit"] >= 3
    assert result.iso_scores["Technical Feasibility"] >= 3
    assert result.pass_gate is True


def test_audit_pipeline_fails_gate_on_low_strategic_alignment():
    pipeline = AuditPipeline()

    idea = {
        "id": "idea-002",
        "dependencies": ["legacy-db", "erp"],
        "workflow_overlap": 2,
        "trend_score": 3,
        "market_risk": 2,
        "strategic_fit": 1,
    }
    context = {
        "data_maturity": 1,
        "competitor_signal": 2,
    }

    result = pipeline.run(idea, context)

    assert result.iso_scores["Strategic Alignment"] == 1
    assert result.pass_gate is False


def test_iso_scores_drop_for_low_operational_readiness():
    pipeline = AuditPipeline()

    idea = {
        "id": "idea-006",
        "dependencies": ["legacy-db", "erp", "crm", "billing"],
        "workflow_overlap": 3,
        "trend_score": 2,
        "market_risk": 4,
        "strategic_fit": 4,
    }
    context = {
        "data_maturity": 1,
        "competitor_signal": 2,
        "service_telemetry": {"uptime": 98.0, "slo_breach_count": 2},
        "incident_history": {"severity": 4},
        "backlog_health": {"delivery_velocity": 1},
        "architecture_metadata": {"legacy_systems": 5},
    }

    result = pipeline.run(idea, context)

    assert result.iso_scores["Technical Feasibility"] <= 2
    assert result.iso_scores["Constraint Fit"] <= 2
    assert result.pass_gate is False


def test_audit_pipeline_fails_gate_for_high_risk_idea():
    pipeline = AuditPipeline()

    idea = {
        "id": "idea-004",
        "description": "Legacy transformation with confidential internal use only data and unclear ownership.",
        "dependencies": ["legacy-db", "erp", "crm", "billing"],
        "workflow_overlap": 3,
        "trend_score": 1,
        "market_risk": 5,
        "strategic_fit": 2,
    }
    context = {
        "data_maturity": 1,
        "competitor_signal": 1,
        "service_telemetry": {"uptime": 98.2, "slo_breach_count": 3},
        "incident_history": {"severity": 4},
        "backlog_health": {"delivery_velocity": 1},
        "architecture_metadata": {"legacy_systems": 5},
    }

    result = pipeline.run(idea, context)

    assert result.pass_gate is False
    assert result.final_score <= 2


def test_audit_pipeline_fails_when_constraint_fit_is_below_threshold():
    pipeline = AuditPipeline()

    idea = {
        "id": "idea-005",
        "description": "Strategic initiative with severe delivery constraints.",
        "dependencies": ["legacy-db", "erp", "crm", "billing"],
        "workflow_overlap": 3,
        "trend_score": 3,
        "market_risk": 4,
        "strategic_fit": 5,
    }
    context = {
        "data_maturity": 1,
        "competitor_signal": 2,
        "service_telemetry": {"uptime": 98.0, "slo_breach_count": 2},
        "incident_history": {"severity": 4},
        "backlog_health": {"delivery_velocity": 1},
        "architecture_metadata": {"legacy_systems": 5},
    }

    result = pipeline.run(idea, context)

    assert result.iso_scores["Strategic Alignment"] == 5
    assert result.iso_scores["Constraint Fit"] < 3
    assert result.iso_scores["Technical Feasibility"] < 3
    assert result.pass_gate is False


def test_audit_pipeline_uses_feedback_history_and_policy_weights():
    pipeline = AuditPipeline()

    idea = {
        "id": "idea-003",
        "dependencies": ["data-platform"],
        "workflow_overlap": 1,
        "trend_score": 4,
        "market_risk": 1,
        "strategic_fit": 4,
    }
    context = {
        "data_maturity": 4,
        "competitor_signal": 3,
        "policy": {"approval_threshold": 4, "weights": {"operational": 0.4, "market": 0.3, "governance": 0.3}},
        "feedback_history": [{"signature": {"strategic_fit": 4, "data_maturity": 4}, "outcome_score": 4}],
    }

    result = pipeline.run(idea, context)

    assert result.policy["approval_threshold"] == 4
    assert result.feedback_adjustment != 0
    assert result.report["recommended_action"]


def test_cli_exports_audit_report(tmp_path):
    idea_path = tmp_path / "idea.json"
    context_path = tmp_path / "context.json"
    output_path = tmp_path / "report.json"

    idea_path.write_text(json.dumps({"id": "idea-cli", "description": "A pilot for workflow automation", "dependencies": ["data-platform"], "workflow_overlap": 0, "trend_score": 4, "market_risk": 1, "strategic_fit": 4}), encoding="utf-8")
    context_path.write_text(json.dumps({"data_maturity": 4, "competitor_signal": 3}), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "agentic_ai_funnel_audit.cli", "--idea-file", str(idea_path), "--context-file", str(context_path), "--output", str(output_path)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )

    assert "idea-cli" in completed.stdout
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["idea_id"] == "idea-cli"
    assert payload["report"]["recommended_action"]
