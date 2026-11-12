"""Agent 3 - Eligibility checking."""
import json

from backend.llm import invoke_json
from prompts.prompts import (ELIGIBILITY_FORMAT, ELIGIBILITY_HUMAN, ELIGIBILITY_SYSTEM)

VALID_STATUS = {"eligible", "ineligible", "potentially_eligible"}


class EligibilityAgent:
    def run(self, query: str, profile: dict, missing: list[str], context: str, sources: dict) -> dict:
        raw = invoke_json(
            ELIGIBILITY_SYSTEM,
            ELIGIBILITY_HUMAN,
            output_format=ELIGIBILITY_FORMAT,
            profile=json.dumps(profile, ensure_ascii=False),
            missing=", ".join(missing) if missing else "none",
            query=query,
            context=context,
        )
        schemes, seen = [], set()
        for item in raw.get("schemes") or []:
            name = (item.get("scheme_name") or "").strip()
            ids = [s for s in (item.get("source_ids") or []) if s in sources]
            # Never show a recommendation without a verifiable source reference.
            if not name or not ids or name.lower() in seen:
                continue
            seen.add(name.lower())
            status = str(item.get("status", "")).lower().strip()
            if status not in VALID_STATUS:
                status = "potentially_eligible"
            schemes.append(
                {
                    "scheme_name": name,
                    "department": item.get("department"),
                    "description": item.get("description") or "",
                    "eligibility_criteria": item.get("eligibility_criteria") or [],
                    "status": status,
                    "reasons": item.get("reasons") or [],
                    "missing_information": item.get("missing_information") or [],
                    "questions_for_user": item.get("questions_for_user") or [],
                    "sources": [sources[s] for s in dict.fromkeys(ids)],
                }
            )
        return {"schemes": schemes, "follow_up_questions": raw.get("follow_up_questions") or []}
