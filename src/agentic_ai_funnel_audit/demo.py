from agentic_ai_funnel_audit.pipeline import AuditPipeline


def main():
    pipeline = AuditPipeline()

    idea = {
        "id": "idea-001",
        "dependencies": ["data-platform", "identity"],
        "workflow_overlap": 1,
        "trend_score": 4,
        "market_risk": 1,
        "strategic_fit": 4,
    }

    context = {
        "data_maturity": 2,
        "competitor_signal": 4,
    }

    result = pipeline.run(idea, context)

    print(f"Idea: {result.idea_id}")
    for eval_item in result.evaluations:
        print(f"- {eval_item.name}: {eval_item.score} ({eval_item.rationale})")
    print(f"- {result.deliberation.name}: {result.deliberation.score} ({result.deliberation.rationale})")
    print("ISO 56001 scores:")
    for domain, score in result.iso_scores.items():
        print(f"  {domain}: {score}")
    print(f"Final gate score: {result.final_score}")
    print(f"Pass gate: {result.pass_gate}")


if __name__ == "__main__":
    main()
