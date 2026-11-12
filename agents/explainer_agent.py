"""Agent 5 - Explainer (plain-English output)."""
import json

from backend.llm import invoke_json
from backend.utils import norm
from prompts.prompts import (EXPLAINER_FORMAT, EXPLAINER_HUMAN, EXPLAINER_SYSTEM,
                             GENERAL_FORMAT, GENERAL_HUMAN, GENERAL_SYSTEM)


class ExplainerAgent:
    def explain_results(self, query: str, cards: list[dict]) -> dict:
        slim = [
            {
                "scheme_name": c["scheme_name"],
                "status": c["status"],
                "description": c["description"],
                "criteria": c["eligibility_criteria"],
                "reasons": c["reasons"],
                "missing_information": c["missing_information"],
            }
            for c in cards
        ]
        raw = invoke_json(
            EXPLAINER_SYSTEM,
            EXPLAINER_HUMAN,
            output_format=EXPLAINER_FORMAT,
            query=query,
            results=json.dumps(slim, ensure_ascii=False),
        )
        explanations = {norm(k): v for k, v in (raw.get("scheme_explanations") or {}).items()}
        return {"summary": raw.get("overall_summary") or "", "explanations": explanations}

    def answer_general(self, query: str, context: str, sources: dict) -> dict:
        raw = invoke_json(
            GENERAL_SYSTEM, GENERAL_HUMAN, output_format=GENERAL_FORMAT, query=query, context=context
        )
        ids = [s for s in (raw.get("source_ids") or []) if s in sources]
        return {"answer": raw.get("answer") or "", "sources": [sources[s] for s in dict.fromkeys(ids)]}
