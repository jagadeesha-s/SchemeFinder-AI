"""Agent 3 - Eligibility checking with the LLM (used only for PDF/TXT sources;
catalog schemes are checked instantly by backend/rules.py)."""
import json

from backend.llm import invoke_json
from prompts.prompts import (ELIGIBILITY_FORMAT, ELIGIBILITY_HUMAN, ELIGIBILITY_SYSTEM)

VALID_STATUS = {"eligible", "ineligible", "potentially_eligible", "insufficient_information"}


class EligibilityAgent:
    def run(self, query: str, profile: dict, missing: list[str], context: str, sources: dict) -> dict:
        if not sources:
            return {"schemes": [], "follow_up_questions": []}
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
            # "potentially" + missing user details = we simply cannot decide yet
            if status == "potentially_eligible" and item.get("missing_information"):
                status = "insufficient_information"
            first = sources[ids[0]]
            schemes.append(
                {
                    "scheme_name": name,
                    "department": item.get("department") or first.get("department") or None,
                    "description": item.get("description") or "",
                    "scheme_level": item.get("scheme_level") or first.get("level") or None,
                    "applicable_state": item.get("applicable_state") or first.get("state") or None,
                    "income_limit": item.get("income_limit"),
                    "benefits": item.get("benefits"),
                    "eligibility_criteria": item.get("eligibility_criteria") or [],
                    "status": status,
                    "reasons": item.get("reasons") or [],
                    "missing_information": item.get("missing_information") or [],
                    "missing_fields": [],
                    "questions_for_user": item.get("questions_for_user") or [],
                    "sources": [sources[s] for s in dict.fromkeys(ids)],
                    "category": first.get("category") or None,
                    "last_verified": first.get("last_verified") or None,
                    "official_url": first.get("official_url") or None,
                    "explanation": "",
                    "application": {},
                    "details": {},
                    "from_catalog": False,
                }
            )
        return {"schemes": schemes, "follow_up_questions": raw.get("follow_up_questions") or []}