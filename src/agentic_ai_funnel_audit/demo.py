from agentic_ai_funnel_audit.pipeline import AuditPipeline


def _print_result(label: str, result, expected: str) -> None:
    print(f"\n=== {label} ===")
    print(f"Expected: {expected}")
    print(f"Idea: {result.idea_id}")
    for eval_item in result.evaluations:
        print(f"- {eval_item.name}: {eval_item.score} ({eval_item.rationale})")
    print(f"- {result.deliberation.name}: {result.deliberation.score} ({result.deliberation.rationale})")
    print("ISO 56001 scores:")
    for domain, score in result.iso_scores.items():
        print(f"  {domain}: {score}")
    print(f"Governance safe: {result.governance['is_safe']}")
    print(f"Governance findings: {result.governance['findings']}")
    print(f"Final gate score: {result.final_score}")
    print(f"Pass gate: {result.pass_gate}")


def main():
    pipeline = AuditPipeline()

    pass_idea = {
        "id": "idea-pass-001",
        "description": "Build a real-time analytics hub for enterprise workflow signals.",
        "dependencies": ["data-platform"],
        "workflow_overlap": 0,
        "trend_score": 4,
        "market_risk": 1,
        "strategic_fit": 4,
        "contains_sensitive_concepts": False,
    }
    pass_context = {
        "data_maturity": 4,
        "competitor_signal": 4,
        "service_telemetry": {"uptime": 99.9, "slo_breach_count": 0},
        "incident_history": {"severity": 1},
        "backlog_health": {"delivery_velocity": 4},
        "architecture_metadata": {"legacy_systems": 1},
    }

    fail_idea = {
        "id": "idea-fail-001",
        "description": "Strategic initiative with severe delivery constraints.",
        "dependencies": ["legacy-db", "erp", "crm", "billing"],
        "workflow_overlap": 3,
        "trend_score": 3,
        "market_risk": 4,
        "strategic_fit": 5,
        "contains_sensitive_concepts": False,
    }
    fail_context = {
        "data_maturity": 1,
        "competitor_signal": 2,
        "service_telemetry": {"uptime": 98.0, "slo_breach_count": 2},
        "incident_history": {"severity": 4},
        "backlog_health": {"delivery_velocity": 1},
        "architecture_metadata": {"legacy_systems": 5},
    }

    _print_result("Scenario A - Balanced readiness", pipeline.run(pass_idea, pass_context), "PASS")
    _print_result("Scenario B - High strategic fit but low feasibility", pipeline.run(fail_idea, fail_context), "FAIL")


if __name__ == "__main__":
    main()
