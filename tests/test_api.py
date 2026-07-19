import time
import json

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
    assert "human_handoff" in response.json()["report"]


def test_batch_audit_endpoint():
    payload = {
        "ideas": [
            {
                "id": "idea-batch-001",
                "title": "Customer churn prevention",
                "description": "Improve retention with governed AI workflows across CRM, billing, and support.",
                "business_outcome": "Reduce churn and improve service responsiveness.",
                "systems_involved": ["crm", "billing", "support"],
                "required_data_sources": ["crm", "billing", "support"],
                "dependencies": ["data-platform", "workflow-engine"],
                "workflow_overlap": 1,
            },
            {
                "id": "idea-batch-002",
                "title": "Governance reporting automation",
                "description": "Automate compliance reporting with workflow orchestration.",
                "business_outcome": "Reduce manual audit preparation effort.",
                "systems_involved": ["crm", "workflow-engine"],
                "required_data_sources": ["crm"],
                "dependencies": ["workflow-engine"],
                "workflow_overlap": 0,
            },
        ],
        "context": {
            "service_telemetry": {"uptime": 99.9, "slo_breach_count": 0},
            "incident_history": {"severity": 1},
            "backlog_health": {"delivery_velocity": 3},
            "architecture_metadata": {"legacy_systems": 1},
        },
    }

    response = client.post("/audit/batch", json=payload)

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert len(response.json()["results"]) == 2
    assert response.json()["results"][0]["idea_id"] == "idea-batch-001"


def test_async_batch_audit_job_endpoint():
    payload = {
        "ideas": [
            {
                "id": "idea-async-001",
                "title": "Customer churn prevention",
                "description": "Improve retention with governed AI workflows across CRM, billing, and support.",
                "business_outcome": "Reduce churn and improve service responsiveness.",
                "systems_involved": ["crm", "billing", "support"],
                "required_data_sources": ["crm", "billing", "support"],
                "dependencies": ["data-platform", "workflow-engine"],
                "workflow_overlap": 1,
            }
        ],
        "context": {
            "service_telemetry": {"uptime": 99.9, "slo_breach_count": 0},
            "incident_history": {"severity": 1},
            "backlog_health": {"delivery_velocity": 3},
            "architecture_metadata": {"legacy_systems": 1, "integration_count": 3},
        },
    }

    submit_response = client.post("/audit/batch/async", json=payload)

    assert submit_response.status_code == 200
    job_id = submit_response.json()["job_id"]

    deadline = time.time() + 2
    latest = None
    while time.time() < deadline:
        latest = client.get(f"/audit/jobs/{job_id}")
        assert latest.status_code == 200
        if latest.json()["status"] == "completed":
            break
        time.sleep(0.05)

    assert latest is not None
    assert latest.json()["status"] == "completed"
    assert latest.json()["results"][0]["idea_id"] == "idea-async-001"
    assert latest.json()["backend"] == "local"


def test_async_batch_pubsub_backend_requires_topic():
    payload = {
        "ideas": [
            {
                "id": "idea-async-pubsub-001",
                "title": "PubSub test",
                "description": "Test pubsub backend configuration.",
            }
        ],
        "async_backend": "pubsub",
    }

    response = client.post("/audit/batch/async", json=payload)

    assert response.status_code == 400
    assert "AGENTIC_PUBSUB_TOPIC" in response.json()["detail"]


def test_audits_list_and_artifact_endpoints():
    payload = {
        "idea": {
            "id": "idea-artifact",
            "description": "A strong innovation review with traceability.",
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
    audit_response = client.post("/audit", json=payload)
    assert audit_response.status_code == 200

    list_response = client.get("/audits")
    assert list_response.status_code == 200
    assert any(item["idea_id"] == "idea-artifact" for item in list_response.json())

    artifact_response = client.get("/audit/idea-artifact/artifact")
    assert artifact_response.status_code == 200
    assert artifact_response.json()["idea"]["id"] == "idea-artifact"


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


def test_enrich_context_endpoint():
    response = client.get("/audit/idea-001/enrich?service_id=analytics-service&team_id=platform-team")
    assert response.status_code == 200
    assert "enriched_context" in response.json()
    assert "service_telemetry" in response.json()["enriched_context"]
    assert "incident_history" in response.json()["enriched_context"]
    assert "backlog_health" in response.json()["enriched_context"]
    assert "architecture_metadata" in response.json()["enriched_context"]


def test_record_and_list_outcomes():
    outcome_payload = {
        "idea_id": "idea-outcome-001",
        "outcome_status": "success",
        "implementation_duration_weeks": 8,
        "actual_delivery_cost": 250000,
        "actual_team_velocity_impact": 2,
        "business_value_realized": 5,
        "risk_incidents_count": 0,
        "technical_debt_added": 1,
        "process_improvements": ["automated-testing"],
        "lessons_learned": "Strong execution and team alignment",
    }
    
    response = client.post("/outcomes", json=outcome_payload)
    assert response.status_code == 200
    assert response.json()["idea_id"] == "idea-outcome-001"
    assert response.json()["outcome_status"] == "success"
    assert "feedback_signal" in response.json()

    list_response = client.get("/outcomes")
    assert list_response.status_code == 200
    assert any(o["idea_id"] == "idea-outcome-001" for o in list_response.json())

    get_response = client.get("/outcomes/idea-outcome-001")
    assert get_response.status_code == 200
    assert get_response.json()["idea_id"] == "idea-outcome-001"


def test_calibration_endpoint():
    response = client.get("/calibration")
    assert response.status_code == 200
    assert "calibration_factors" in response.json()
    assert "total_outcomes_recorded" in response.json()
    assert "feedback_history_size" in response.json()


def test_knowledge_base_status_endpoint():
    response = client.get("/knowledge-base/status")

    assert response.status_code == 200
    assert response.json()["mode"] in {"demo", "production"}
    domains = response.json()["domains"]
    assert any(item["domain"] == "market" for item in domains)
    assert all("refresh_mode" in item for item in domains)


def test_knowledge_base_ingestion_endpoint():
    payload = {
        "domain": "market",
        "owner": "market-intelligence",
        "source_system": "analyst-feed",
        "refresh_mode": "async",
        "refresh_cadence": "daily",
        "content_type": "markdown",
        "title": "New trend snapshot",
        "content": "Macro trend shows stronger cost pressure and higher demand for governed AI.",
        "metadata": {"trend_score": 4, "market_risk": 2},
    }

    response = client.post("/knowledge-base/ingest", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["domain"] == "market"


def test_knowledge_base_sync_endpoint(tmp_path, monkeypatch):
    strategy_feed = tmp_path / "strategy.json"
    strategy_feed.write_text(
        json.dumps(
            [
                {
                    "title": "Q3 Strategic Priorities",
                    "content": "Prioritize retention and governed AI execution.",
                    "metadata": {"priority_score": 4, "themes": ["retention", "governance"]},
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTIC_SOURCE_STRATEGY_DOCS", str(strategy_feed))

    response = client.post("/knowledge-base/sync", json={"source_types": ["strategy_docs"]})

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["ingested_count"] >= 1
