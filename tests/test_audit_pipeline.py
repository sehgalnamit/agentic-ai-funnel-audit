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
