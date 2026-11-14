"""Rule-based eligibility check. No LLM, no embeddings -> instant and consistent.

Status meanings
  eligible                - every recorded rule was checked and passed, AND the record is marked
                            rules_complete + active + has a last_verified date
  potentially_eligible    - nothing failed, but some rules are unverified or need manual confirmation
  insufficient_information- a rule exists but the user has not given the needed detail
  ineligible              - at least one recorded rule clearly fails (or scheme is closed)"""
from backend.utils import norm
import db_config

STATUS_ORDER = {"eligible": 0, "potentially_eligible": 1, "insufficient_information": 2, "ineligible": 3}

MISSING_LABELS = {
    "age": "your age", "state": "your state/UT", "gender": "your gender",
    "category": "your social category", "annual_income": "your annual family income",
    "occupation": "your occupation", "education": "your education",
}
MISSING_QUESTIONS = {
    "age": "What is your age?",
    "state": "Which state or Union Territory do you live in?",
    "gender": "What is your gender?",
    "category": "Which category do you belong to (General, OBC, SC, ST, EWS)?",
    "annual_income": "What is your total annual family income (in ₹)?",
    "occupation": "What is your occupation?",
    "education": "What is your highest level of education?",
}


def _n(value) -> str:
    return str(int(value)) if value is not None and float(value).is_integer() else str(value)


def state_applies(rec: dict, state: str | None) -> bool:
    applicable = (rec.get("applicable_state") or "").strip()
    if not applicable or norm(applicable).startswith("all india") or not state:
        return True
    return norm(state) in norm(applicable)


def matches_filters(rec: dict, category=None, level=None, state=None) -> bool:
    if category and category not in rec["categories"]:
        return False
    if level == "Central" and rec["level"] != "Central":
        return False
    if level in ("State", "UT", "State/UT") and rec["level"] not in ("State", "UT"):
        return False
    return state_applies(rec, state)


def rule_summary(rec: dict) -> list[str]:
    """Human-readable list of the structured rules stored for a scheme."""
    out = []
    if rec["min_age"] is not None or rec["max_age"] is not None:
        lo = _n(rec["min_age"]) if rec["min_age"] is not None else "-"
        hi = _n(rec["max_age"]) if rec["max_age"] is not None else "-"
        out.append(f"Age: {lo} to {hi}")
    if rec["gender"]:
        out.append(f"Gender: {rec['gender']}")
    if rec["social_categories"]:
        out.append("Social category: " + ", ".join(rec["social_categories"]))
    if rec["income_limit_annual"] is not None:
        out.append(f"Annual family income up to ₹{int(rec['income_limit_annual']):,}")
    if rec["occupations"]:
        out.append("Occupation: " + ", ".join(rec["occupations"]))
    if rec["min_education"]:
        out.append(f"Minimum education: {rec['min_education']}")
    if rec["land_required"]:
        out.append("Land ownership required")
    return out


def evaluate(rec: dict, profile: dict) -> dict:
    fails, passes, missing, manual = [], [], [], []

    if rec["status"] in ("closed", "discontinued"):
        return {"status": "ineligible", "missing": [], "manual": [],
                "reasons": [f"This scheme is marked '{rec['status']}' in the database."]}

    # --- state / region
    applicable = (rec.get("applicable_state") or "").strip()
    if applicable and not norm(applicable).startswith("all india"):
        user_state = profile.get("state")
        if not user_state:
            missing.append("state")
        elif norm(user_state) in norm(applicable):
            passes.append(f"The scheme applies to {applicable}, which includes your state.")
        else:
            fails.append(f"The scheme applies to {applicable}, not {user_state}.")

    # --- age
    lo, hi = rec["min_age"], rec["max_age"]
    if lo is not None or hi is not None:
        age = profile.get("age")
        if age is None:
            missing.append("age")
        elif lo is not None and age < lo:
            fails.append(f"Minimum age is {_n(lo)}; you are {age}.")
        elif hi is not None and age > hi:
            fails.append(f"Maximum age is {_n(hi)}; you are {age}.")
        else:
            passes.append(f"Your age ({age}) is within the allowed range.")

    # --- gender
    want = (rec.get("gender") or "").strip().lower()
    if want in ("female", "male", "transgender"):
        gender = (profile.get("gender") or "").lower()
        if not gender:
            missing.append("gender")
        elif gender == want:
            passes.append(f"The scheme is for {rec['gender'].lower()} applicants, which matches you.")
        else:
            fails.append(f"The scheme is only for {rec['gender'].lower()} applicants.")

    # --- social category
    if rec["social_categories"]:
        cat = profile.get("category")
        allowed = [c.lower() for c in rec["social_categories"]]
        if not cat:
            missing.append("category")
        elif cat.lower() in allowed:
            passes.append(f"Your category ({cat}) is covered.")
        else:
            fails.append("The scheme is for " + ", ".join(rec["social_categories"]) + f"; you selected {cat}.")

    # --- income
    limit = rec["income_limit_annual"]
    if limit is not None:
        income = profile.get("annual_income")
        if income is None:
            missing.append("annual_income")
        elif income <= limit:
            passes.append(f"Your family income (₹{int(income):,}) is within the limit of ₹{int(limit):,}.")
        else:
            fails.append(f"The income limit is ₹{int(limit):,}; your family income is ₹{int(income):,}.")

    # --- occupation
    if rec["occupations"]:
        occ = (profile.get("occupation") or "").lower()
        if not occ:
            missing.append("occupation")
        elif any(k in occ for k in rec["occupations"]):
            passes.append("Your occupation matches the scheme.")
        else:
            fails.append("The scheme is for: " + ", ".join(rec["occupations"]) + f". Your occupation: {profile.get('occupation')}.")

    # --- education
    if rec["min_education"]:
        order = db_config.EDUCATION_ORDER
        edu = profile.get("education")
        if edu not in order or rec["min_education"] not in order:
            if not edu:
                missing.append("education")
        elif order.index(edu) >= order.index(rec["min_education"]):
            passes.append(f"Your education ({edu}) meets the minimum ({rec['min_education']}).")
        else:
            fails.append(f"Minimum education is {rec['min_education']}; you selected {edu}.")

    # --- rules we cannot check from the profile
    if rec["land_required"]:
        manual.append("land ownership (not part of your profile)")

    verified = rec["rules_complete"] and bool(rec["last_verified"]) and rec["status"] == "active"
    if fails:
        status = "ineligible"
    elif missing:
        status = "insufficient_information"
    elif manual:
        status = "potentially_eligible"
    elif verified:
        status = "eligible"
    else:
        status = "potentially_eligible"

    reasons = list(fails) + passes
    if manual:
        reasons.append("Please confirm: " + "; ".join(manual) + ".")
    if status == "potentially_eligible" and not manual:
        if passes:
            reasons.append("The details you gave match, but this scheme's rules are not fully verified in the database - confirm on the official portal.")
        else:
            reasons.append("No machine-checkable rules are recorded for this scheme - read the official eligibility conditions below.")
    if status == "insufficient_information":
        reasons.append("Add the missing details to get a proper check.")
    if status == "eligible" and not passes:
        reasons.append("No specific restrictions are recorded for this scheme.")
    return {"status": status, "reasons": reasons, "missing": list(dict.fromkeys(missing)), "manual": manual}


def build_card(rec: dict, profile: dict) -> dict:
    res = evaluate(rec, profile)
    official = rec["source_url"] or rec["official_url"] or ""
    income_text = rec["income_limit"] or (
        f"Up to ₹{int(rec['income_limit_annual']):,} per year" if rec["income_limit_annual"] is not None else None)
    short = rec["short_description"] or (rec["detailed_description"] or "")[:240] or None
    return {
        "scheme_id": rec["id"],
        "scheme_name": rec["scheme_name"],
        "department": rec["department"],
        "description": short,
        "scheme_level": rec["level"],
        "applicable_state": rec["applicable_state"],
        "income_limit": income_text,
        "benefits": rec["benefits"],
        "eligibility_criteria": rec["eligibility"],
        "status": res["status"],
        "reasons": res["reasons"],
        "missing_fields": res["missing"],
        "missing_information": [MISSING_LABELS.get(f, f) for f in res["missing"]],
        "questions_for_user": [],
        "sources": [{
            "id": rec["id"], "file": rec.get("_file", "catalog"), "page": 0,
            "source_document": rec["source_document"], "official_url": official,
            "last_verified": rec["last_verified"] or "",
        }],
        "category": rec["category"],
        "categories": rec["categories"],
        "last_verified": rec["last_verified"],
        "official_url": rec["official_url"] or rec["source_url"],
        "explanation": "",
        "application": {
            "required_documents": rec["required_documents"],
            "application_steps": rec["application_process"],
            "deadline": rec["deadline"],
            "official_link": rec["official_url"] or rec["source_url"],
            "notes": None,
        },
        "details": {
            "detailed_description": rec["detailed_description"],
            "aliases": rec["aliases"],
            "scheme_status": rec["status"],
            "rules": rule_summary(rec),
            "source_url": rec["source_url"],
        },
        "from_catalog": True,
    }