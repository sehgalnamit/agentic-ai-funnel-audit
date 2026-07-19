from agentic_ai_funnel_audit.ui.app import app


def test_ui_app_imports():
    assert app is not None


def test_ui_exposes_knowledge_base_route():
    client = app.test_client()

    response = client.get("/knowledge-base")

    assert response.status_code == 200
    assert b"Demo Knowledge Base" in response.data
    assert b"strategy agent KB" in response.data
