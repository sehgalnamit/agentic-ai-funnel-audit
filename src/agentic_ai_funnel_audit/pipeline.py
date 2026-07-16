from dataclasses import dataclass
from typing import Dict, Any, List

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
        final_score = self._aggregate_score([internal, market, deliberative, safety])
        pass_gate = (
            final_score >= 3
            and iso_scores["Strategic Alignment"] >= 3
            and safety.score >= 3
            and governance["is_safe"]
        )

        return AuditResult(
            idea_id=idea.get("id", "unknown"),
            evaluations=[internal, market, safety],
            deliberation=deliberative,
            iso_scores=iso_scores,
            final_score=final_score,
            pass_gate=pass_gate,
            safety=safety,
            governance=governance,
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
