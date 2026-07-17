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
        data_maturity = context.get("data_maturity", 3)
        workflow_overlap = idea.get("workflow_overlap", 0)
        service_telemetry = context.get("service_telemetry") or {}
        incident_history = context.get("incident_history") or {}
        backlog_health = context.get("backlog_health") or {}
        architecture_metadata = context.get("architecture_metadata") or {}

        risk_penalty = 0
        risk_penalty += min(3, len(dependencies))
        risk_penalty += min(2, workflow_overlap)
        if service_telemetry.get("slo_breach_count", 0) > 0:
            risk_penalty += 1
        if service_telemetry.get("uptime", 100) < 99.0:
            risk_penalty += 1
        if incident_history.get("severity", 0) >= 3:
            risk_penalty += 1
        if backlog_health.get("delivery_velocity", 3) <= 2:
            risk_penalty += 1
        if architecture_metadata.get("legacy_systems", 0) > 2:
            risk_penalty += 1

        # Higher score means better operational readiness, lower score means higher risk.
        readiness_score = min(5, max(1, data_maturity + 2 - risk_penalty))

        rationale = (
            f"Dependencies: {len(dependencies)}, "
            f"Data maturity: {data_maturity}, "
            f"Workflow overlap: {workflow_overlap}."
        )

        return AgentEvaluation(
            name=self.name,
            score=readiness_score,
            rationale=rationale,
            details={
                "dependencies": dependencies,
                "data_maturity": data_maturity,
                "workflow_overlap": workflow_overlap,
                "service_telemetry": service_telemetry,
                "incident_history": incident_history,
                "backlog_health": backlog_health,
                "architecture_metadata": architecture_metadata,
            },
        )


class MarketSignalAgent(Agent):
    def __init__(self):
        super().__init__("Market Signal Agent")

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        trend_score = idea.get("trend_score", 3)
        competitor_signal = context.get("competitor_signal", 3)
        market_risk = idea.get("market_risk", 2)

        # Convert market risk into a positive readiness contribution.
        market_readiness = round((trend_score + competitor_signal + (5 - market_risk)) / 3)
        score = min(5, max(1, market_readiness))
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
