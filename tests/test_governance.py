from agentic_ai_funnel_audit.governance import ModelArmor, SafetyAgent


def test_model_armor_inspects_safe_idea():
    idea = {
        "description": "A strategic innovation proposal for workflow optimization.",
        "contains_sensitive_concepts": False,
    }
    armor = ModelArmor()
    findings = armor.inspect(idea)

    assert findings["is_safe"] is True
    assert findings["policy"] == "Enterprise Decision Governance"
    assert isinstance(findings["findings"], list)


def test_safety_agent_flags_sensitive_description():
    idea = {
        "description": "This idea includes an API key and confidential internal use only data.",
    }
    safety = SafetyAgent().evaluate(idea, {})

    assert safety.score == 2
    assert "Potential sensitive or proprietary content detected" in safety.rationale
    assert len(safety.details["flags"]) > 0
