from fastapi.testclient import TestClient

from agentic_ai_funnel_audit.api import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_audit_endpoint():
    payload = {
        "idea": {
            "id": "idea-001",
            "description": "A strategic innovation proposal for workflow optimization.",
            "dependencies": ["data-platform"],
            "workflow_overlap": 0,
            "trend_score": 4,
            "market_risk": 1,
            "strategic_fit": 4,
            "contains_sensitive_concepts": False,
        },
        "context": {
            "data_maturity": 4,
            "competitor_signal": 3,
            "service_telemetry": {"uptime": 99.9, "slo_breach_count": 0},
            "incident_history": {"count": 1, "severity": 2},
            "backlog_health": {"delivery_velocity": 3, "tech_debt": 2},
            "architecture_metadata": {"legacy_systems": 1, "integration_count": 4},
        },
    }
    response = client.post(
        "/audit",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["idea_id"] == "idea-001"
    assert "final_score" in response.json()
    assert "report" in response.json()
    assert response.json()["report"]["executive_summary"]


def test_dashboard_endpoint():
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "CTAO" in response.text
    assert "use the /audit endpoint" in response.text.lower()


def test_audit_override():
    payload = {
        "idea": {
            "id": "idea-override",
            "description": "A strategic innovation proposal for workflow optimization.",
            "dependencies": ["data-platform"],
            "workflow_overlap": 0,
            "trend_score": 4,
            "market_risk": 1,
            "strategic_fit": 4,
            "contains_sensitive_concepts": False,
        },
        "context": {
            "data_maturity": 4,
            "competitor_signal": 3,
        },
    }
    response = client.post("/audit", json=payload)
    assert response.status_code == 200

    override_payload = {
        "override_reason": "Executive decision to fund a pilot despite the score.",
        "approved": True,
        "reviewer": "CTO",
    }
    override_response = client.post("/audit/idea-override/override", json=override_payload)

    assert override_response.status_code == 200
    assert override_response.json()["idea_id"] == "idea-override"
    assert override_response.json()["override"]["approved"] is True
