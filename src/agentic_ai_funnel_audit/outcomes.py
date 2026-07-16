"""
Outcome tracking for capturing post-decision data and feedback loop calibration.
Enables continuous improvement of recommendation accuracy over time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid


@dataclass
class OutcomeRecord:
    """Record of a decision outcome captured post-implementation."""

    idea_id: str
    outcome_status: str  # "success", "partial", "failure", "abandoned"
    implementation_duration_weeks: int
    actual_delivery_cost: float
    actual_team_velocity_impact: int  # -10 to +10
    business_value_realized: int  # 1-5 score
    risk_incidents_count: int
    technical_debt_added: int  # 1-5
    process_improvements: List[str] = field(default_factory=list)
    lessons_learned: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_feedback_signal(self) -> Dict[str, Any]:
        """Convert outcome to a feedback signal for calibration."""
        success_score = 5 if self.outcome_status == "success" else (3 if self.outcome_status == "partial" else 1)
        return {
            "idea_id": self.idea_id,
            "outcome_status": self.outcome_status,
            "success_score": success_score,
            "delivery_efficiency": 5 - min(4, self.implementation_duration_weeks // 4),
            "cost_efficiency": max(1, 5 - int(self.actual_delivery_cost / 100000)),
            "team_impact": 3 + self.actual_team_velocity_impact // 5,
            "business_value": self.business_value_realized,
            "risk_score": max(1, 5 - self.risk_incidents_count),
        }


class OutcomeStore:
    """In-memory store for outcome records and feedback signals."""

    def __init__(self):
        self._outcomes: Dict[str, OutcomeRecord] = {}
        self._feedback_history: List[Dict[str, Any]] = []

    def record_outcome(self, idea_id: str, outcome: OutcomeRecord) -> OutcomeRecord:
        """Record an outcome for a completed idea."""
        self._outcomes[idea_id] = outcome
        feedback = outcome.to_feedback_signal()
        self._feedback_history.append(feedback)
        return outcome

    def get_outcome(self, idea_id: str) -> OutcomeRecord | None:
        """Retrieve an outcome record."""
        return self._outcomes.get(idea_id)

    def list_outcomes(self) -> List[OutcomeRecord]:
        """List all recorded outcomes."""
        return list(self._outcomes.values())

    def get_feedback_history(self) -> List[Dict[str, Any]]:
        """Get all feedback signals for calibration."""
        return self._feedback_history

    def compute_calibration_factors(self) -> Dict[str, float]:
        """Compute feedback calibration factors from historical outcomes."""
        if not self._feedback_history:
            return {
                "delivery_accuracy": 1.0,
                "cost_accuracy": 1.0,
                "risk_accuracy": 1.0,
                "business_value_accuracy": 1.0,
            }

        outcomes = [o.to_feedback_signal() for o in self._outcomes.values()]
        if not outcomes:
            return {
                "delivery_accuracy": 1.0,
                "cost_accuracy": 1.0,
                "risk_accuracy": 1.0,
                "business_value_accuracy": 1.0,
            }

        avg_success = sum(o["success_score"] for o in outcomes) / len(outcomes)
        avg_delivery = sum(o["delivery_efficiency"] for o in outcomes) / len(outcomes)
        avg_cost = sum(o["cost_efficiency"] for o in outcomes) / len(outcomes)
        avg_risk = sum(o["risk_score"] for o in outcomes) / len(outcomes)
        avg_value = sum(o["business_value"] for o in outcomes) / len(outcomes)

        return {
            "delivery_accuracy": avg_delivery / 3.0,
            "cost_accuracy": avg_cost / 3.0,
            "risk_accuracy": avg_risk / 3.0,
            "business_value_accuracy": avg_value / 3.0,
            "overall_success_rate": avg_success / 5.0,
        }


class FeedbackLoopCalibrator:
    """Applies feedback loop calibration to improve future scoring."""

    def __init__(self, outcome_store: OutcomeStore):
        self.outcome_store = outcome_store

    def compute_feedback_adjustment(self, idea_characteristics: Dict[str, Any]) -> int:
        """
        Compute feedback adjustment based on similar past outcomes.
        Returns a -2 to +2 score adjustment for future similar ideas.
        """
        feedback_history = self.outcome_store.get_feedback_history()
        if not feedback_history:
            return 0

        signature_matches = []
        for entry in feedback_history:
            overlap = 0
            if entry.get("outcome_status") == idea_characteristics.get("expected_outcome"):
                overlap += 2
            if abs(entry.get("delivery_efficiency", 3) - idea_characteristics.get("estimated_delivery", 3)) <= 1:
                overlap += 1
            if abs(entry.get("business_value", 3) - idea_characteristics.get("estimated_value", 3)) <= 1:
                overlap += 1
            if overlap > 0:
                signature_matches.append((overlap, entry["success_score"]))

        if not signature_matches:
            return 0

        signature_matches.sort(reverse=True)
        top_matches = signature_matches[:3]
        avg_success = sum(s[1] for s in top_matches) / len(top_matches)

        return max(-2, min(2, int((avg_success - 3) / 1.5)))
