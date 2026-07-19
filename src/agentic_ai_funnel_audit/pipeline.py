from dataclasses import dataclass
from typing import Dict, Any, List

from statistics import mean

from .agents import (
    AgentEvaluation,
    StrategicAlignmentAgent,
    DataReadinessAgent,
    ArchitectureReadinessAgent,
    DeliveryCapacityAgent,
    InternalOperationsAgent,
    MarketSignalAgent,
    DeliberativeSandboxAgent,
)
from .governance import ModelArmor, SafetyAgent
from .knowledge_base import load_knowledge_base
from .modeling import ModelEvaluator


@dataclass
class AuditResult:
    idea_id: str
    evaluations: List[AgentEvaluation]
    deliberation: AgentEvaluation
    iso_scores: Dict[str, int]
    final_score: int
    pass_gate: bool
    safety: AgentEvaluation
    governance: Dict[str, Any]
    policy: Dict[str, Any]
    feedback_adjustment: int
    report: Dict[str, Any]
    artifact: Dict[str, Any]


class AuditPipeline:
    def __init__(self):
        self.strategic_agent = StrategicAlignmentAgent()
        self.data_agent = DataReadinessAgent()
        self.architecture_agent = ArchitectureReadinessAgent()
        self.delivery_agent = DeliveryCapacityAgent()
        self.internal_agent = InternalOperationsAgent()
        self.market_agent = MarketSignalAgent()
        self.deliberative_agent = DeliberativeSandboxAgent()
        self.safety_agent = SafetyAgent()
        self.model_armor = ModelArmor()
        self.model_evaluator = ModelEvaluator()
        self.knowledge_base = load_knowledge_base()

    def run(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AuditResult:
        runtime_context = dict(context)
        runtime_context.setdefault("knowledge_base", self.knowledge_base)
        governance = self.model_armor.inspect(idea)
        strategic = self.strategic_agent.evaluate(idea, runtime_context)
        data = self.data_agent.evaluate(idea, runtime_context)
        runtime_context["data_readiness_score"] = data.score
        architecture = self.architecture_agent.evaluate(idea, runtime_context)
        runtime_context["architecture_readiness_score"] = architecture.score
        delivery = self.delivery_agent.evaluate(idea, runtime_context)
        runtime_context["delivery_capacity_score"] = delivery.score
        safety = self.safety_agent.evaluate(idea, runtime_context)
        internal = self.internal_agent.evaluate(idea, runtime_context)
        market = self.market_agent.evaluate(idea, runtime_context)
        model_insights = self._build_model_insights(idea, runtime_context)
        internal, market = self._apply_model_insights(internal, market, model_insights)
        deliberative = self.deliberative_agent.evaluate([strategic, data, architecture, delivery, internal, market, safety])

        iso_scores = self._score_iso_domains(strategic, data, architecture, delivery, internal, market, safety)
        policy = self._resolve_policy(runtime_context)
        feedback_adjustment = self._compute_feedback_adjustment(idea, runtime_context)
        weighted_score = self._apply_policy_weights(
            strategic=strategic,
            data=data,
            architecture=architecture,
            delivery=delivery,
            internal=internal,
            market=market,
            safety=safety,
            deliberative=deliberative,
            policy=policy,
        )
        final_score = max(1, min(5, round(weighted_score + feedback_adjustment)))
        pass_gate = (
            final_score >= policy.get("approval_threshold", 3)
            and iso_scores["Strategic Alignment"] >= 3
            and iso_scores["Constraint Fit"] >= 3
            and iso_scores["Technical Feasibility"] >= 3
            and iso_scores["Compliance Readiness"] >= 3
            and governance["is_safe"]
        )
        report = self._build_report(
            idea,
            runtime_context,
            strategic,
            data,
            architecture,
            delivery,
            internal,
            market,
            safety,
            iso_scores,
            final_score,
            pass_gate,
            governance,
            model_insights,
        )
        artifact = self._build_audit_artifact(
            idea,
            runtime_context,
            iso_scores,
            final_score,
            pass_gate,
            governance,
            policy,
            report,
            model_insights,
        )

        return AuditResult(
            idea_id=idea.get("id", "unknown"),
            evaluations=[strategic, data, architecture, delivery, internal, market, safety],
            deliberation=deliberative,
            iso_scores=iso_scores,
            final_score=final_score,
            pass_gate=pass_gate,
            safety=safety,
            governance=governance,
            policy=policy,
            feedback_adjustment=feedback_adjustment,
            report=report,
            artifact=artifact,
        )

    def run_batch(self, ideas: List[Dict[str, Any]], shared_context: Dict[str, Any] | None = None) -> List[AuditResult]:
        base_context = shared_context or {}
        results: List[AuditResult] = []
        for idea in ideas:
            context = dict(base_context)
            context.update(idea.get("context_overrides") or {})
            results.append(self.run(idea, context))
        return results

    def _score_iso_domains(
        self,
        strategic: AgentEvaluation,
        data: AgentEvaluation,
        architecture: AgentEvaluation,
        delivery: AgentEvaluation,
        internal: AgentEvaluation,
        market: AgentEvaluation,
        safety: AgentEvaluation,
    ) -> Dict[str, int]:
        strategic_alignment = min(5, max(1, strategic.score))
        constraint_fit = min(5, max(1, round((data.score + delivery.score + market.score) / 3)))
        technical_feasibility = min(5, max(1, round((architecture.score + internal.score) / 2)))
        compliance_readiness = min(5, max(1, safety.score))

        return {
            "Strategic Alignment": strategic_alignment,
            "Constraint Fit": constraint_fit,
            "Technical Feasibility": technical_feasibility,
            "Compliance Readiness": compliance_readiness,
        }

    def _aggregate_score(self, evaluations: List[AgentEvaluation]) -> int:
        return round(sum(e.score for e in evaluations) / len(evaluations))

    def _resolve_policy(self, context: Dict[str, Any]) -> Dict[str, Any]:
        policy = context.get("policy") or {}
        return {
            "approval_threshold": policy.get("approval_threshold", 3),
            "weights": policy.get("weights") or {
                "strategic": 0.2,
                "data": 0.2,
                "architecture": 0.1,
                "delivery": 0.1,
                "operational": 0.1,
                "market": 0.15,
                "governance": 0.25,
            },
        }

    def _apply_policy_weights(
        self,
        strategic: AgentEvaluation,
        data: AgentEvaluation,
        architecture: AgentEvaluation,
        delivery: AgentEvaluation,
        internal: AgentEvaluation,
        market: AgentEvaluation,
        safety: AgentEvaluation,
        deliberative: AgentEvaluation,
        policy: Dict[str, Any],
    ) -> float:
        weights = policy.get("weights", {})
        has_custom_weights = bool(weights)
        strategic_weight = weights.get("strategic", 0.0 if has_custom_weights else 0.2)
        data_weight = weights.get("data", 0.0 if has_custom_weights else 0.2)
        architecture_weight = weights.get("architecture", 0.0 if has_custom_weights else 0.1)
        delivery_weight = weights.get("delivery", 0.0 if has_custom_weights else 0.1)
        operational_weight = weights.get("operational", 0.1 if not has_custom_weights else 0.0)
        market_weight = weights.get("market", 0.15 if not has_custom_weights else 0.0)
        governance_weight = weights.get("governance", 0.25 if not has_custom_weights else 0.0)
        deliberative_weight = 0.1

        weighted_sum = (
            strategic.score * strategic_weight
            + data.score * data_weight
            + architecture.score * architecture_weight
            + delivery.score * delivery_weight
            + internal.score * operational_weight
            + market.score * market_weight
            + safety.score * governance_weight
            + deliberative.score * deliberative_weight
        )
        total_weight = strategic_weight + data_weight + architecture_weight + delivery_weight + operational_weight + market_weight + governance_weight + deliberative_weight
        return weighted_sum / total_weight

    def _compute_feedback_adjustment(self, idea: Dict[str, Any], context: Dict[str, Any]) -> int:
        history = context.get("feedback_history") or []
        if not history:
            return 0

        matches = []
        for entry in history:
            signature = entry.get("signature") or {}
            if not signature:
                continue
            overlap = 0
            for key, value in signature.items():
                if idea.get(key) == value or context.get(key) == value:
                    overlap += 1
            matches.append(overlap)

        if not matches:
            return 0

        return round(mean(matches) / max(1, len(matches)))

    def _build_model_insights(self, idea: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.model_evaluator.is_enabled():
            return {}

        safe_context = {key: value for key, value in context.items() if key != "knowledge_base"}

        return {
            "operational": self.model_evaluator.evaluate(idea, safe_context, "operational"),
            "market": self.model_evaluator.evaluate(idea, safe_context, "market"),
        }

    def _apply_model_insights(
        self,
        internal: AgentEvaluation,
        market: AgentEvaluation,
        model_insights: Dict[str, Any],
    ) -> tuple[AgentEvaluation, AgentEvaluation]:
        if not model_insights:
            return internal, market

        operational_insight = model_insights.get("operational")
        market_insight = model_insights.get("market")

        if operational_insight:
            internal.score = round((internal.score + operational_insight["score"]) / 2)
            internal.rationale += " | Model-informed operational insight applied."
            internal.details["model_operational"] = operational_insight

        if market_insight:
            market.score = round((market.score + market_insight["score"]) / 2)
            market.rationale += " | Model-informed market insight applied."
            market.details["model_market"] = market_insight

        return internal, market

    def _build_report(
        self,
        idea: Dict[str, Any],
        context: Dict[str, Any],
        strategic: AgentEvaluation,
        data: AgentEvaluation,
        architecture: AgentEvaluation,
        delivery: AgentEvaluation,
        internal: AgentEvaluation,
        market: AgentEvaluation,
        safety: AgentEvaluation,
        iso_scores: Dict[str, int],
        final_score: int,
        pass_gate: bool,
        governance: Dict[str, Any],
        model_insights: Dict[str, Any],
    ) -> Dict[str, Any]:
        recommended_action = "Proceed with a controlled pilot" if pass_gate else "Rework the proposal before funding"
        investment = self._build_investment_recommendation(strategic, data, architecture, delivery, internal, market, pass_gate)
        report = {
            "executive_summary": (
                f"{idea.get('id', 'idea')} received a {final_score}/5 score and {'passed' if pass_gate else 'did not pass'} the review gate."
            ),
            "recommended_action": recommended_action,
            "iso_scores": iso_scores,
            "governance_findings": governance.get("findings", []),
            "safety_status": safety.rationale,
            "investment_recommendation": investment,
            "evidence_by_agent": {
                strategic.name: strategic.details.get("evidence", []),
                data.name: data.details.get("evidence", []),
                architecture.name: architecture.details.get("evidence", []),
                delivery.name: delivery.details.get("evidence", []),
                internal.name: internal.details.get("evidence", []),
                market.name: market.details.get("evidence", []),
                safety.name: safety.details.get("evidence", []),
            },
            "context_sources": [
                key for key in ["service_telemetry", "incident_history", "backlog_health", "architecture_metadata"]
                if key in context
            ] + ["knowledge_base"],
        }

        if model_insights:
            report["model_insights"] = {
                lens: {
                    "score": insight["score"],
                    "rationale": insight["rationale"],
                }
                for lens, insight in model_insights.items()
            }

        return report

    def _build_investment_recommendation(
        self,
        strategic: AgentEvaluation,
        data: AgentEvaluation,
        architecture: AgentEvaluation,
        delivery: AgentEvaluation,
        internal: AgentEvaluation,
        market: AgentEvaluation,
        pass_gate: bool,
    ) -> Dict[str, Any]:
        if pass_gate:
            return {
                "route": "fund_pilot_now",
                "summary": "Idea has enough current readiness to proceed to a controlled pilot.",
                "priority_investments": ["pilot delivery", "measurement", "governance controls"],
                "estimated_investment_band": "medium",
            }

        if strategic.score >= 4 and data.score <= 2:
            return {
                "route": "fund_foundation_first",
                "summary": "Idea is strategically strong but blocked by data readiness. Invest in data foundations before pilot funding.",
                "priority_investments": ["data integration", "data quality", "ownership and lineage"],
                "estimated_investment_band": "medium-high",
            }

        if strategic.score >= 4 and architecture.score <= 2:
            return {
                "route": "incubate_architecture",
                "summary": "Idea is valuable but technical complexity is high. Resolve architecture and delivery constraints before launch.",
                "priority_investments": ["platform integration", "workflow redesign", "delivery capacity"],
                "estimated_investment_band": "medium-high",
            }

        if strategic.score >= 4 and delivery.score <= 2:
            return {
                "route": "expand_delivery_capacity",
                "summary": "Idea is promising but delivery bandwidth is weak. Improve team capacity or sequencing before committing to the pilot.",
                "priority_investments": ["team capacity", "delivery sequencing", "platform enablement"],
                "estimated_investment_band": "medium",
            }

        if market.score <= 2:
            return {
                "route": "retest_market_case",
                "summary": "Current macro and micro trend evidence is weak. Revalidate market demand before funding build work.",
                "priority_investments": ["customer discovery", "competitive analysis", "value hypothesis refinement"],
                "estimated_investment_band": "low-medium",
            }

        return {
            "route": "rework_then_resubmit",
            "summary": "The idea needs better evidence or prerequisites before funding.",
            "priority_investments": ["business case refinement", "capability gap closure"],
            "estimated_investment_band": "low",
        }

    def _build_audit_artifact(
        self,
        idea: Dict[str, Any],
        context: Dict[str, Any],
        iso_scores: Dict[str, int],
        final_score: int,
        pass_gate: bool,
        governance: Dict[str, Any],
        policy: Dict[str, Any],
        report: Dict[str, Any],
        model_insights: Dict[str, Any],
    ) -> Dict[str, Any]:
        safe_context = {
            key: value
            for key, value in context.items()
            if key != "knowledge_base"
        }
        return {
            "idea": idea,
            "context": safe_context,
            "iso_scores": iso_scores,
            "final_score": final_score,
            "pass_gate": pass_gate,
            "governance": governance,
            "policy": policy,
            "report": report,
            "model_insights": model_insights,
            "generated_by": "agentic-ai-funnel-audit",
        }
