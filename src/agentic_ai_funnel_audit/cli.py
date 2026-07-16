import argparse
import json
from pathlib import Path

from .pipeline import AuditPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the agentic funnel audit workflow from the command line.")
    parser.add_argument("--idea-file", required=True, help="Path to a JSON file containing the idea payload")
    parser.add_argument("--context-file", help="Optional path to a JSON file containing context")
    parser.add_argument("--output", help="Optional path to write the audit report as JSON")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    idea_path = Path(args.idea_file)
    with idea_path.open("r", encoding="utf-8") as handle:
        idea = json.load(handle)

    context = {}
    if args.context_file:
        context_path = Path(args.context_file)
        with context_path.open("r", encoding="utf-8") as handle:
            context = json.load(handle)

    pipeline = AuditPipeline()
    result = pipeline.run(idea, context)
    payload = {
        "idea_id": result.idea_id,
        "final_score": result.final_score,
        "pass_gate": result.pass_gate,
        "iso_scores": result.iso_scores,
        "policy": result.policy,
        "feedback_adjustment": result.feedback_adjustment,
        "report": result.report,
    }

    print(json.dumps(payload, indent=2))

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
