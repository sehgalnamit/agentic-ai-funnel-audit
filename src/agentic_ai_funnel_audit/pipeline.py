from dataclasses import dataclass
from typing import Dict, Any, List

from statistics import mean

from .agents import (
    AgentEvaluation,
    InternalOperationsAgent,
    MarketSignalAgent,
    DeliberativeSandboxAgent,
)
from .governance import ModelArmor, SafetyAgent


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


class AuditPipeline:
    def __init__(self):
        self.internal_agent = InternalOperationsAgent()
        self.market_agent = MarketSignalAgent()
        self.deliberative_agent = DeliberativeSandboxAgent()
        self.safety_agent = SafetyAgent()
        self.model_armor = ModelArmor()

    def run(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AuditResult:
        governance = self.model_armor.inspect(idea)
        safety = self.safety_agent.evaluate(idea, context)
        internal = self.internal_agent.evaluate(idea, context)
        market = self.market_agent.evaluate(idea, context)
        deliberative = self.deliberative_agent.evaluate([internal, market, safety])

        iso_scores = self._score_iso_domains(idea, internal, market, safety)
        policy = self._resolve_policy(context)
        feedback_adjustment = self._compute_feedback_adjustment(idea, context)
        weighted_score = self._apply_policy_weights(
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
            and safety.score >= 3
            and governance["is_safe"]
        )
        report = self._build_report(idea, context, iso_scores, final_score, pass_gate, governance, safety)

        return AuditResult(
            idea_id=idea.get("id", "unknown"),
            evaluations=[internal, market, safety],
            deliberation=deliberative,
            iso_scores=iso_scores,
            final_score=final_score,
            pass_gate=pass_gate,
            safety=safety,
            governance=governance,
            policy=policy,
            feedback_adjustment=feedback_adjustment,
            report=report,
        )

    def _score_iso_domains(
        self,
        idea: Dict[str, Any],
        internal: AgentEvaluation,
        market: AgentEvaluation,
        safety: AgentEvaluation,
    ) -> Dict[str, int]:
        strategic_alignment = min(5, max(1, idea.get("strategic_fit", 3)))
        constraint_fit = min(5, max(1, 6 - max(internal.score, market.score)))
        technical_feasibility = min(5, max(1, 6 - internal.score))
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
            "weights": policy.get("weights") or {"operational": 0.35, "market": 0.25, "governance": 0.4},
        }

    def _apply_policy_weights(
        self,
        internal: AgentEvaluation,
        market: AgentEvaluation,
        safety: AgentEvaluation,
        deliberative: AgentEvaluation,
        policy: Dict[str, Any],
    ) -> float:
        weights = policy.get("weights", {})
        operational_weight = weights.get("operational", 0.35)
        market_weight = weights.get("market", 0.25)
        governance_weight = weights.get("governance", 0.4)

        return (
            internal.score * operational_weight
            + market.score * market_weight
            + safety.score * governance_weight
            + deliberative.score * 0.1
        )

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

    def _build_report(
        self,
        idea: Dict[str, Any],
        context: Dict[str, Any],
        iso_scores: Dict[str, int],
        final_score: int,
        pass_gate: bool,
        governance: Dict[str, Any],
        safety: AgentEvaluation,
    ) -> Dict[str, Any]:
        recommended_action = "Proceed with a controlled pilot" if pass_gate else "Rework the proposal before funding"
        return {
            "executive_summary": (
                f"{idea.get('id', 'idea')} received a {final_score}/5 score and {'passed' if pass_gate else 'did not pass'} the review gate."
            ),
            "recommended_action": recommended_action,
            "iso_scores": iso_scores,
            "governance_findings": governance.get("findings", []),
            "safety_status": safety.rationale,
            "context_sources": [
                key for key in ["service_telemetry", "incident_history", "backlog_health", "architecture_metadata"]
                if key in context
            ],
        }
