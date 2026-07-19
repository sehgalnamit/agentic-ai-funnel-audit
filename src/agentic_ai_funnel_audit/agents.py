from dataclasses import dataclass
from typing import Any, Dict, List

from .knowledge_base import DemoKnowledgeBase


def _clamp_score(value: int) -> int:
    return min(5, max(1, int(value)))


def _csv_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _build_query(idea: Dict[str, Any], *fields: str) -> str:
    parts: list[str] = []
    for field in fields:
        value = idea.get(field)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def _evidence_from_hits(hits: list[Any]) -> list[dict[str, Any]]:
    return [hit.to_dict() for hit in hits]


@dataclass
class AgentEvaluation:
    name: str
    score: int
    rationale: str
    details: Dict[str, Any]


class Agent:
    def __init__(self, name: str):
        self.name = name

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        raise NotImplementedError("Agent.evaluate must be implemented by subclasses.")

    def _knowledge_base(self, context: Dict[str, Any]) -> DemoKnowledgeBase | None:
        kb = context.get("knowledge_base")
        return kb if isinstance(kb, DemoKnowledgeBase) else None


class StrategicAlignmentAgent(Agent):
    def __init__(self):
        super().__init__("Strategic Alignment Agent")

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        explicit = idea.get("strategic_fit")
        kb = self._knowledge_base(context)
        query = _build_query(idea, "title", "description", "business_outcome", "target_users", "kpi_target")
        hits = kb.search("strategy", query, limit=3) if kb and query else []

        if explicit is not None:
            score = _clamp_score(explicit)
            rationale = "Strategic fit provided explicitly; KB evidence used for explanation only."
        elif hits:
            score_signals = [int(hit.document.metadata.get("priority_score", 3)) for hit in hits]
            score = _clamp_score(round(sum(score_signals) / len(score_signals)))
            themes = []
            for hit in hits:
                themes.extend(_csv_items(hit.document.metadata.get("themes", [])))
            rationale = (
                "Strategic score derived from retrieved strategy themes: "
                + ", ".join(sorted(set(themes))[:4])
                if themes
                else "Strategic score derived from retrieved strategy documents."
            )
        else:
            score = 3
            rationale = "No strategy evidence retrieved, so strategic alignment stays neutral pending document mapping."

        return AgentEvaluation(
            name=self.name,
            score=score,
            rationale=rationale,
            details={
                "query": query,
                "evidence": _evidence_from_hits(hits),
            },
        )


class DataReadinessAgent(Agent):
    def __init__(self):
        super().__init__("Data Readiness Agent")

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        explicit = context.get("data_maturity")
        required_sources = idea.get("required_data_sources") or idea.get("data_sources") or []
        required_items = _csv_items(required_sources)
        kb = self._knowledge_base(context)
        query = " ".join(required_items) or _build_query(idea, "description", "business_outcome", "title")
        hits = kb.search("data", query, limit=3) if kb and query else []

        matched_sources: set[str] = set()
        kb_scores: list[int] = []
        for hit in hits:
            matched_sources.update(_csv_items(hit.document.metadata.get("covered_sources", [])))
            kb_scores.append(int(hit.document.metadata.get("maturity_score", 3)))

        missing_sources = sorted(source for source in required_items if source.lower() not in {item.lower() for item in matched_sources})
        if kb_scores:
            derived_score = round(sum(kb_scores) / len(kb_scores))
            derived_score -= min(2, len(missing_sources))
        else:
            derived_score = 3

        if explicit is not None and not hits:
            score = _clamp_score(explicit)
            rationale = "Data maturity came from explicit context because no KB evidence matched the requested sources."
        else:
            score = _clamp_score(derived_score if explicit is None else round((derived_score * 2 + int(explicit)) / 3))
            rationale = "Data readiness derived from KB evidence about covered sources and known maturity gaps."
            if missing_sources:
                rationale += f" Missing sources: {', '.join(missing_sources)}."

        return AgentEvaluation(
            name=self.name,
            score=score,
            rationale=rationale,
            details={
                "required_data_sources": required_items,
                "missing_sources": missing_sources,
                "evidence": _evidence_from_hits(hits),
            },
        )


class InternalOperationsAgent(Agent):
    def __init__(self):
        super().__init__("Internal Operations Agent")

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        dependencies = idea.get("dependencies") or idea.get("systems_involved") or []
        dependency_list = _csv_items(dependencies)
        data_readiness = context.get("data_readiness_score", context.get("data_maturity", 3))
        workflow_overlap = int(idea.get("workflow_overlap", 0))
        service_telemetry = context.get("service_telemetry") or {}
        incident_history = context.get("incident_history") or {}
        backlog_health = context.get("backlog_health") or {}
        architecture_metadata = context.get("architecture_metadata") or {}
        kb = self._knowledge_base(context)
        query = " ".join(dependency_list) or _build_query(idea, "description", "title", "current_process")
        tech_hits = kb.search("technology", query, limit=3) if kb and query else []

        risk_penalty = 0
        risk_penalty += min(3, len(dependency_list))
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
        if tech_hits and len(dependency_list) >= 4:
            risk_penalty += 1

        readiness_score = _clamp_score(int(data_readiness) + 2 - risk_penalty)
        rationale = (
            f"Dependencies: {len(dependency_list)}, data readiness: {data_readiness}, "
            f"workflow overlap: {workflow_overlap}."
        )
        if tech_hits:
            rationale += f" Retrieved {len(tech_hits)} technology KB document(s) to estimate integration complexity."

        return AgentEvaluation(
            name=self.name,
            score=readiness_score,
            rationale=rationale,
            details={
                "dependencies": dependency_list,
                "data_readiness": data_readiness,
                "workflow_overlap": workflow_overlap,
                "service_telemetry": service_telemetry,
                "incident_history": incident_history,
                "backlog_health": backlog_health,
                "architecture_metadata": architecture_metadata,
                "evidence": _evidence_from_hits(tech_hits),
            },
        )


class MarketSignalAgent(Agent):
    def __init__(self):
        super().__init__("Market Signal Agent")

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        explicit_trend = idea.get("trend_score")
        explicit_competitor = context.get("competitor_signal")
        explicit_risk = idea.get("market_risk")
        kb = self._knowledge_base(context)
        query = _build_query(idea, "title", "description", "business_outcome", "target_users")
        hits = kb.search("market", query, limit=3) if kb and query else []

        if hits:
            trend_score = round(sum(int(hit.document.metadata.get("trend_score", 3)) for hit in hits) / len(hits))
            competitor_signal = round(sum(int(hit.document.metadata.get("competitor_signal", 3)) for hit in hits) / len(hits))
            market_risk = round(sum(int(hit.document.metadata.get("market_risk", 3)) for hit in hits) / len(hits))
        else:
            trend_score = 3
            competitor_signal = 3
            market_risk = 2

        if explicit_trend is not None:
            trend_score = int(explicit_trend)
        if explicit_competitor is not None:
            competitor_signal = int(explicit_competitor)
        if explicit_risk is not None:
            market_risk = int(explicit_risk)

        market_readiness = round((trend_score + competitor_signal + (5 - market_risk)) / 3)
        score = _clamp_score(market_readiness)
        rationale = (
            f"Trend score: {trend_score}, competitor signal: {competitor_signal}, market risk: {market_risk}."
        )
        if hits:
            macro_factors = []
            micro_factors = []
            for hit in hits:
                macro_factors.extend(_csv_items(hit.document.metadata.get("macro_factors", [])))
                micro_factors.extend(_csv_items(hit.document.metadata.get("micro_factors", [])))
            rationale += (
                " Macro factors checked: " + ", ".join(sorted(set(macro_factors))[:3]) + "."
                if macro_factors
                else ""
            )
            rationale += (
                " Micro factors checked: " + ", ".join(sorted(set(micro_factors))[:3]) + "."
                if micro_factors
                else ""
            )

        return AgentEvaluation(
            name=self.name,
            score=score,
            rationale=rationale,
            details={
                "trend_score": trend_score,
                "competitor_signal": competitor_signal,
                "market_risk": market_risk,
                "evidence": _evidence_from_hits(hits),
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
        low_confidence = [e.name for e in evaluations if not e.details.get("evidence")]
        rationale = "Balanced score from all agent perspectives."

        if high_risk:
            rationale += " A low score was detected by at least one specialized agent, indicating a critical implementation risk."
        if low_confidence:
            rationale += f" Evidence depth is limited for: {', '.join(low_confidence)}."

        details = {
            "component_scores": [{"agent": e.name, "score": e.score} for e in evaluations],
            "average_score": average_score,
            "low_evidence_agents": low_confidence,
        }

        return AgentEvaluation(
            name=self.name,
            score=average_score,
            rationale=rationale,
            details=details,
        )
