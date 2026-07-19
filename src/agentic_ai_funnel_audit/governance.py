import re
from typing import Dict, Any, List

from .agents import Agent, AgentEvaluation
from .knowledge_base import DemoKnowledgeBase


def _build_sensitive_patterns() -> List[re.Pattern]:
    return [
        re.compile(r"\b(?:ssn|social security number|credit card|card number|passport number)\b", re.IGNORECASE),
        re.compile(r"\b(?:secret|confidential|proprietary|internal use only)\b", re.IGNORECASE),
        re.compile(r"\b(?:password|api key|access token|private key)\b", re.IGNORECASE),
    ]


class SafetyAgent(Agent):
    def __init__(self):
        super().__init__("Safety Agent")
        self.sensitive_patterns = _build_sensitive_patterns()

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any]) -> AgentEvaluation:
        description = idea.get("description", "")
        flags = []
        kb = context.get("knowledge_base") if isinstance(context.get("knowledge_base"), DemoKnowledgeBase) else None

        for pattern in self.sensitive_patterns:
            if pattern.search(description):
                flags.append(pattern.pattern)

        hits = kb.search("governance", description, limit=2) if kb and description else []

        score = 5
        rationale = "No sensitive content detected."
        if flags:
            score = 2
            rationale = (
                "Potential sensitive or proprietary content detected in idea description. "
                f"Patterns: {flags}."
            )
        elif hits:
            rationale = "Governance policies retrieved with no immediate sensitive-content violation."

        return AgentEvaluation(
            name=self.name,
            score=score,
            rationale=rationale,
            details={
                "description_length": len(description),
                "flags": flags,
                "evidence": [hit.to_dict() for hit in hits],
            },
        )


class ModelArmor:
    """A lightweight guardrail layer for model prompts and idea content."""

    def __init__(self):
        self.policy_name = "Enterprise Decision Governance"
        self.encouraged_checks = ["safety", "proprietary content", "hallucination risk"]

    def inspect(self, idea: Dict[str, Any]) -> Dict[str, Any]:
        description = idea.get("description", "")
        findings = []

        if len(description) < 20:
            findings.append("Idea description is short; consider adding more context.")
        if idea.get("contains_sensitive_concepts"):
            findings.append("Explicit sensitive concept flag is set on the idea.")

        safe = True
        if any(keyword in description.lower() for keyword in ["password", "api key", "private key"]):
            safe = False
            findings.append("Potential secret material detected.")

        return {
            "policy": self.policy_name,
            "is_safe": safe,
            "findings": findings,
            "checked_fields": ["description", "contains_sensitive_concepts"],
        }
