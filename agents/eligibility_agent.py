"""Agent 3 - Eligibility checking with the LLM (used only for PDF/TXT sources;
catalog schemes are checked instantly and exactly by backend/rules.py).

The LLM only reports PASS / FAIL / UNKNOWN for each condition it finds in the excerpts.
The FINAL status is computed in Python (rules.derive_status), so the model can never
declare someone "eligible" on its own."""
import json

from backend.llm import invoke_json
from backend.rules import FIELD_FOR_CONDITION, MISSING_LABELS, derive_status, missing_from
from prompts.prompts import (ELIGIBILITY_FORMAT, ELIGIBILITY_HUMAN, ELIGIBILITY_SYSTEM)

VALID_RESULTS = {"PASS", "FAIL", "UNKNOWN"}


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
            first = sources[ids[0]]

            conditions = []
            for c in item.get("conditions") or []:
                result = str(c.get("result", "")).upper().strip()
                cname = c.get("name") if c.get("name") in FIELD_FOR_CONDITION else "Other"
                reason = c.get("reason") or ""
                # a condition without a valid source cannot count as verified
                if c.get("source_id") not in sources:
                    result, reason = "UNKNOWN", (reason + " (no supporting source given)").strip()
                if result not in VALID_RESULTS:
                    result = "UNKNOWN"
                conditions.append({
                    "name": cname, "requirement": c.get("requirement") or "", "result": result,
                    "reason": reason, "mandatory": c.get("mandatory", True) is not False,
                    "field": FIELD_FOR_CONDITION.get(cname),
                })

            # Documents are "verified" only when their source record says so.
            verified = bool(first.get("last_verified")) and first.get("status", "active") == "active" and bool(conditions)
            status = derive_status(conditions, verified) if conditions else "potentially_eligible"
            if not conditions:
                conditions.append({
                    "name": "Other", "requirement": "", "result": "UNKNOWN", "mandatory": False, "field": None,
                    "reason": "No explicit eligibility conditions were found in the retrieved excerpts - verify on the official source.",
                })
            miss = missing_from(conditions, profile)
            warnings = []
            if not first.get("last_verified"):
                warnings.append("This document has not been verified yet (no last-verified date).")
            if first.get("status") and first["status"] != "active":
                warnings.append(f"Scheme status: {first['status'].replace('_', ' ')} - confirm it is currently open.")

            schemes.append({
                "scheme_name": name,
                "department": item.get("department") or first.get("department") or None,
                "description": item.get("description") or "",
                "scheme_level": item.get("scheme_level") or first.get("level") or None,
                "applicable_state": item.get("applicable_state") or first.get("state") or None,
                "income_limit": item.get("income_limit"),
                "benefits": item.get("benefits"),
                "eligibility_criteria": [c["requirement"] for c in conditions if c["requirement"]],
                "status": status,
                "conditions": conditions,
                "reasons": [f"{c['name']}: {c['reason']}" for c in conditions],
                "missing_fields": miss,
                "missing_information": [MISSING_LABELS.get(f, f) for f in miss],
                "questions_for_user": item.get("questions_for_user") or [],
                "relevance": 0,
                "relevance_reasons": [],
                "verification_warnings": warnings,
                "sources": [sources[s] for s in dict.fromkeys(ids)],
                "category": first.get("category") or None,
                "categories": [first["category"]] if first.get("category") else [],
                "last_verified": first.get("last_verified") or None,
                "official_url": first.get("official_url") or None,
                "source_url": first.get("official_url") or None,
                "explanation": "",
                "application": {},
                "details": {},
                "from_catalog": False,
            })
        return {"schemes": schemes, "follow_up_questions": raw.get("follow_up_questions") or []}