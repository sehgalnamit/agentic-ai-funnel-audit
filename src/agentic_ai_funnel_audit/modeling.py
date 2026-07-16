import os
from typing import Any, Dict


class ModelEvaluator:
    def __init__(self):
        self.use_model = os.getenv("AGENTIC_USE_MODEL", "false").lower() in ("1", "true", "yes")
        self.model_name = os.getenv("AGENTIC_MODEL_NAME", "gpt-4o-mini")
        self.openai = None
        self.api_key = os.getenv("OPENAI_API_KEY")

        if self.api_key:
            try:
                import openai

                self.openai = openai
                self.openai.api_key = self.api_key
            except Exception:
                self.openai = None

    def is_enabled(self) -> bool:
        return self.use_model and self.openai is not None

    def evaluate(self, idea: Dict[str, Any], context: Dict[str, Any], lens: str) -> Dict[str, Any]:
        if self.is_enabled():
            return self._call_model(idea, context, lens)

        return self._heuristic_evaluate(idea, context, lens)

    def _prompt_text(self, idea: Dict[str, Any], context: Dict[str, Any], lens: str) -> str:
        return (
            f"Evaluate the following idea for {lens} risk and opportunity. "
            f"Use a 1-5 score, clear rationale, and identify any key signals. "
            f"Idea: {idea.get('description')}\n"
            f"Dependencies: {idea.get('dependencies')}\n"
            f"Context: {context}\n"
        )

    def _call_model(self, idea: Dict[str, Any], context: Dict[str, Any], lens: str) -> Dict[str, Any]:
        prompt = self._prompt_text(idea, context, lens)
        try:
            response = self.openai.ChatCompletion.create(
                model=self.model_name,
                messages=[{"role": "system", "content": "You are an enterprise audit scoring assistant."}, {"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content.strip()
            score, rationale = self._parse_model_response(content)
            return {
                "score": score,
                "rationale": rationale,
                "details": {"lens": lens, "model_response": content},
            }
        except Exception as exc:
            return {
                "score": 3,
                "rationale": f"Model evaluation failed, fallback used. Error: {exc}",
                "details": {"lens": lens, "fallback": True},
            }

    def _parse_model_response(self, response: str) -> tuple[int, str]:
        score = 3
        rationale = response
        for line in response.splitlines():
            if line.lower().startswith("score"):
                try:
                    score = int("".join(filter(str.isdigit, line)))
                except ValueError:
                    score = 3
        return max(1, min(5, score)), rationale

    def _heuristic_evaluate(self, idea: Dict[str, Any], context: Dict[str, Any], lens: str) -> Dict[str, Any]:
        if lens == "operational":
            base = 3
            base -= int(context.get("data_maturity", 3) < 3)
            base -= int((context.get("service_telemetry") or {}).get("slo_breach_count", 0) > 0)
            score = max(1, min(5, base))
            rationale = "Heuristic operational scoring based on maturity and recent incidents."
        else:
            base = idea.get("trend_score", 3) + context.get("competitor_signal", 3) - idea.get("market_risk", 2)
            score = max(1, min(5, base))
            rationale = "Heuristic market scoring based on trend and competitor signal."

        return {
            "score": score,
            "rationale": rationale,
            "details": {"lens": lens, "heuristic": True},
        }
