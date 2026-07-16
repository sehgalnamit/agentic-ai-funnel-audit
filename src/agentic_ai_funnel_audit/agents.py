from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class AgentEvaluation:
    name: str
    score: int
    rationale: str
    details: Dict[str, Any]


class Agent:
    """Base agent for independent evaluation tasks."""

    def __init__(self, name: str):
        self.name = name

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        raise NotImplementedError("Agent.evaluate must be implemented by subclasses.")


class InternalOperationsAgent(Agent):
    def __init__(self):
        super().__init__("Internal Operations Agent")

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        dependencies = idea.get("dependencies", [])
        data_maturity = context.get("data_maturity", 0)
        workflow_overlap = idea.get("workflow_overlap", 0)
        risk_score = min(5, max(1, 5 - data_maturity + len(dependencies) + workflow_overlap))

        rationale = (
            f"Dependencies: {len(dependencies)}, "
            f"Data maturity: {data_maturity}, "
            f"Workflow overlap: {workflow_overlap}."
        )

        return AgentEvaluation(
            name=self.name,
            score=risk_score,
            rationale=rationale,
            details={
                "dependencies": dependencies,
                "data_maturity": data_maturity,
                "workflow_overlap": workflow_overlap,
            },
        )


class MarketSignalAgent(Agent):
    def __init__(self):
        super().__init__("Market Signal Agent")

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        trend_score = idea.get("trend_score", 3)
        competitor_signal = context.get("competitor_signal", 3)
        market_risk = idea.get("market_risk", 2)

        score = min(5, max(1, trend_score + competitor_signal - market_risk))
        rationale = (
            f"Trend score: {trend_score}, "
            f"Competitor signal: {competitor_signal}, "
            f"Market risk: {market_risk}."
        )

        return AgentEvaluation(
            name=self.name,
            score=score,
            rationale=rationale,
            details={
                "trend_score": trend_score,
                "competitor_signal": competitor_signal,
                "market_risk": market_risk,
            },
        )


class DeliberativeSandboxAgent(Agent):
    def __init__(self):
        super().__init__("Deliberative Sandbox")

    def evaluate(self, evaluations: List[AgentEvaluation]) -> AgentEvaluation:
        if not evaluations:
            raise ValueError("DeliberativeSandboxAgent requires at least one agent evaluation.")

        average_score = round(sum(e.score for e in evaluations) / len(evaluations))
        high_risk = any(e.score <= 2 for e in evaluations)
        rationale = "Balanced score from all agent perspectives."

        if high_risk:
            rationale += " A low score was detected by at least one specialized agent, indicating a critical implementation risk."

        details = {
            "component_scores": [{"agent": e.name, "score": e.score} for e in evaluations],
            "average_score": average_score,
        }

        return AgentEvaluation(
            name=self.name,
            score=average_score,
            rationale=rationale,
            details=details,
        )
