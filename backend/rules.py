"""Rule-based, THREE-VALUED eligibility check (no LLM, no embeddings -> instant and consistent).

Every recorded condition becomes PASS / FAIL / UNKNOWN:
  PASS    the user's value meets the condition
  FAIL    the user's value does not meet the condition
  UNKNOWN the user did not give the needed detail, or it cannot be checked from the profile

Final status
  ineligible               at least one mandatory condition FAILS
  insufficient_information a mandatory condition is UNKNOWN and none FAIL
  eligible                 every mandatory condition PASSES *and* the record is verified
                           (rules_complete + active + last_verified)
  potentially_eligible     evidence is positive but the record is not fully verified
A matching category or occupation alone NEVER makes a user eligible."""
import db_config
from backend.catalog import load_catalog
from backend.utils import norm

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
STATUS_ORDER = {"eligible": 0, "potentially_eligible": 1, "insufficient_information": 2, "ineligible": 3}

MISSING_LABELS = {
    "age": "your age", "state": "your state/UT", "gender": "your gender",
    "category": "your social category", "annual_income": "your annual family income",
    "occupation": "your occupation", "education": "your education",
    "land_owner": "whether you own agricultural land",
    "residence": "whether you live in a rural or urban area", "bpl": "your BPL status",
    "minority": "your minority-community status", "disability": "your disability status",
    "ex_serviceman": "your ex-serviceman status", "marital_status": "your marital status",
}
MISSING_QUESTIONS = {
    "age": "What is your age?",
    "state": "Which state or Union Territory do you live in?",
    "gender": "What is your gender?",
    "category": "Which category do you belong to (General, OBC, SC, ST, EWS)?",
    "annual_income": "What is your total annual family income (in ₹)?",
    "occupation": "What is your occupation?",
    "education": "What is your highest level of education?",
    "land_owner": "Do you own agricultural land?",
    "residence": "Do you live in a rural or urban area?",
    "bpl": "Does your family hold Below Poverty Line (BPL) status?",
    "minority": "Do you belong to a notified minority community?",
    "disability": "Do you have a disability?",
    "ex_serviceman": "Are you an ex-serviceman?",
    "marital_status": "What is your marital status?",
}
FIELD_FOR_CONDITION = {
    "Age": "age", "State": "state", "Income": "annual_income", "Social category": "category",
    "Gender": "gender", "Occupation": "occupation", "Education": "education", "Land ownership": "land_owner",
    "Residence": "residence", "BPL status": "bpl", "Minority status": "minority",
    "Disability": "disability", "Ex-serviceman": "ex_serviceman", "Marital status": "marital_status",
}


def _n(value) -> str:
    return str(int(value)) if value is not None and float(value).is_integer() else str(value)


def cond(name, requirement, result, reason, mandatory=True) -> dict:
    return {"name": name, "requirement": requirement, "result": result, "reason": reason,
            "mandatory": mandatory, "field": FIELD_FOR_CONDITION.get(name)}


# ------------------------------------------------------------ status logic
def derive_status(conditions: list[dict], verified: bool) -> str:
    mandatory = [c for c in conditions if c["mandatory"]]
    if any(c["result"] == FAIL for c in mandatory):
        return "ineligible"
    if any(c["result"] == UNKNOWN for c in mandatory):
        return "insufficient_information"
    unverified_note = any(c["result"] == UNKNOWN for c in conditions)   # optional/unverified items
    if verified and not unverified_note:
        return "eligible"
    return "potentially_eligible"


def missing_from(conditions: list[dict], profile: dict) -> list[str]:
    """Profile fields the user still has to provide (only for UNKNOWN mandatory conditions)."""
    out = []
    for c in conditions:
        field = c.get("field")
        if c["mandatory"] and c["result"] == UNKNOWN and field and profile.get(field) in (None, ""):
            out.append(field)
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------- scoping
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
    if rec.get("area"):
        out.append(f"Residence: {rec['area']} areas")
    for key, label in (("bpl_required", "BPL family"), ("minority_required", "Notified minority community"),
                       ("disability_required", "Person with disability"), ("ex_serviceman_required", "Ex-serviceman")):
        if rec.get(key):
            out.append(f"Required: {label}")
    return out


# --------------------------------------------------------------- evaluation
def evaluate(rec: dict, profile: dict) -> dict:
    conds: list[dict] = []

    if rec["status"] in ("closed", "discontinued"):
        conds.append(cond("Scheme status", "Scheme must be open", FAIL,
                          f"This scheme is marked '{rec['status']}' in the database."))
        return {"status": "ineligible", "conditions": conds, "missing": []}

    # State / region
    applicable = (rec.get("applicable_state") or "").strip()
    if applicable and not norm(applicable).startswith("all india"):
        st = profile.get("state")
        req = f"Applies to {applicable}"
        if not st:
            conds.append(cond("State", req, UNKNOWN, "Your state/UT was not provided."))
        elif norm(st) in norm(applicable):
            conds.append(cond("State", req, PASS, f"You live in {st}."))
        else:
            conds.append(cond("State", req, FAIL, f"The scheme applies to {applicable}, not {st}."))

    # Age
    lo, hi = rec["min_age"], rec["max_age"]
    if lo is not None or hi is not None:
        req = "Age " + (f"{_n(lo)}" if lo is not None else "any") + " to " + (f"{_n(hi)}" if hi is not None else "any")
        age = profile.get("age")
        if age is None:
            conds.append(cond("Age", req, UNKNOWN, "Your age was not provided."))
        elif lo is not None and age < lo:
            conds.append(cond("Age", req, FAIL, f"Minimum age is {_n(lo)}; you are {age}."))
        elif hi is not None and age > hi:
            conds.append(cond("Age", req, FAIL, f"Maximum age is {_n(hi)}; you are {age}."))
        else:
            conds.append(cond("Age", req, PASS, f"Your age ({age}) is within the range."))

    # Gender
    want = (rec.get("gender") or "").strip().lower()
    if want in ("female", "male", "transgender"):
        req = f"For {rec['gender']} applicants"
        gender = (profile.get("gender") or "").lower()
        if not gender:
            conds.append(cond("Gender", req, UNKNOWN, "Your gender was not provided."))
        elif gender == want:
            conds.append(cond("Gender", req, PASS, "Your gender matches."))
        else:
            conds.append(cond("Gender", req, FAIL, f"The scheme is only for {rec['gender'].lower()} applicants."))

    # Social category
    if rec["social_categories"]:
        req = "For " + ", ".join(rec["social_categories"])
        cat = profile.get("category")
        if not cat:
            conds.append(cond("Social category", req, UNKNOWN, "Your social category was not provided."))
        elif cat.lower() in [c.lower() for c in rec["social_categories"]]:
            conds.append(cond("Social category", req, PASS, f"Your category ({cat}) is covered."))
        else:
            conds.append(cond("Social category", req, FAIL, f"You selected {cat}; the scheme is for {', '.join(rec['social_categories'])}."))

    # Income
    limit = rec["income_limit_annual"]
    if limit is not None:
        req = f"Annual family income up to ₹{int(limit):,}"
        income = profile.get("annual_income")
        if income is None:
            conds.append(cond("Income", req, UNKNOWN, "Your family income was not provided."))
        elif income <= limit:
            conds.append(cond("Income", req, PASS, f"Your income (₹{int(income):,}) is within the limit."))
        else:
            conds.append(cond("Income", req, FAIL, f"Your income (₹{int(income):,}) is above the limit."))

    # Occupation
    if rec["occupations"]:
        req = "Occupation: " + ", ".join(rec["occupations"])
        occ = (profile.get("occupation") or "").lower()
        if not occ:
            conds.append(cond("Occupation", req, UNKNOWN, "Your occupation was not provided."))
        elif any(k in occ for k in rec["occupations"]):
            conds.append(cond("Occupation", req, PASS, "Your occupation matches."))
        else:
            conds.append(cond("Occupation", req, FAIL, f"Your occupation ({profile.get('occupation')}) does not match."))

    # Education
    if rec["min_education"]:
        order = db_config.EDUCATION_ORDER
        req = f"At least {rec['min_education']}"
        edu = profile.get("education")
        eff = db_config.EDUCATION_EQUIV.get(edu, edu)
        if not edu:
            conds.append(cond("Education", req, UNKNOWN, "Your education was not provided."))
        elif eff not in order or rec["min_education"] not in order:
            conds.append(cond("Education", req, UNKNOWN, "Your education level could not be compared."))
        elif order.index(eff) >= order.index(rec["min_education"]):
            note = f" (counted as '{eff}')" if eff != edu else ""
            conds.append(cond("Education", req, PASS, f"Your education ({edu}){note} meets the minimum."))
        else:
            conds.append(cond("Education", req, FAIL, f"Minimum education is {rec['min_education']}; you selected {edu}."))

    # Land ownership
    if rec["land_required"]:
        land = profile.get("land_owner")
        if land == "Yes":
            conds.append(cond("Land ownership", "Must own agricultural land", PASS,
                              "You said you own land (ownership records still need to be checked)."))
        elif land == "No":
            conds.append(cond("Land ownership", "Must own agricultural land", FAIL, "You said you do not own agricultural land."))
        else:
            conds.append(cond("Land ownership", "Must own agricultural land", UNKNOWN, "Land ownership was not provided."))

    # Residence (rural / urban)
    if rec.get("area"):
        req = f"{rec['area']} residents"
        res = profile.get("residence")
        if not res:
            conds.append(cond("Residence", req, UNKNOWN, "Whether you live in a rural or urban area was not provided."))
        elif res.lower() == rec["area"].lower():
            conds.append(cond("Residence", req, PASS, f"You live in a {res.lower()} area."))
        else:
            conds.append(cond("Residence", req, FAIL, f"The scheme is for {rec['area'].lower()} areas; you live in a {res.lower()} area."))

    # Yes/No requirements
    for key, name, field, label in (
            ("bpl_required", "BPL status", "bpl", "Below Poverty Line (BPL) family"),
            ("minority_required", "Minority status", "minority", "Notified minority community"),
            ("disability_required", "Disability", "disability", "Person with disability"),
            ("ex_serviceman_required", "Ex-serviceman", "ex_serviceman", "Ex-serviceman")):
        if rec.get(key):
            val = profile.get(field)
            if val == "Yes":
                conds.append(cond(name, label, PASS, "You answered Yes."))
            elif val == "No":
                conds.append(cond(name, label, FAIL, "You answered No."))
            else:
                conds.append(cond(name, label, UNKNOWN, "You did not answer this question."))

    # Free-text official conditions we could not turn into rules (informational, not mandatory)
    if rec["eligibility"] and not rec["rules_complete"]:
        conds.append(cond("Other official conditions", "; ".join(rec["eligibility"]), UNKNOWN,
                          "Not machine-verified - read the conditions and confirm on the official portal.",
                          mandatory=False))

    verified = rec["rules_complete"] and bool(rec["last_verified"]) and rec["status"] == "active"
    return {"status": derive_status(conds, verified), "conditions": conds, "missing": missing_from(conds, profile)}


# ---------------------------------------------------------------- relevance
OCCUPATION_HINTS = [
    (("student", "studying", "pursuing", "scholar"), "Education", "you are a student"),
    (("farmer", "agricultur", "cultivat", "kisan", "grower"), "Agriculture", "you are a farmer"),
    (("unemploy", "jobless", "job seeker", "looking for job"), "Employment", "you are looking for work"),
    (("artisan", "weaver", "craft", "carpenter", "potter", "tailor", "blacksmith", "labour", "daily wage"), "Employment", "your trade/work"),
    (("self-employed", "self employed", "business", "entrepreneur", "shopkeeper", "vendor", "trader", "startup"), "Business", "you run or plan a business"),
]


def profile_categories(profile: dict) -> dict:
    """{category: (weight, reason)} - what the profile suggests is relevant. Used for ranking only."""
    hints: dict = {}

    def add(cat, weight, reason):
        if cat not in hints or hints[cat][0] < weight:
            hints[cat] = (weight, reason)

    occ = (profile.get("occupation") or "").lower()
    for words, cat, reason in OCCUPATION_HINTS:
        if any(w in occ for w in words):
            add(cat, db_config.STRONG_RELEVANCE, f"Relevant because {reason}")
    if profile.get("category") in ("SC", "ST", "OBC"):
        add("SC/ST/OBC Welfare", db_config.STRONG_RELEVANCE, f"Relevant because your category is {profile['category']}")
    if (profile.get("education") or "").startswith("Pursuing"):
        add("Education", db_config.STRONG_RELEVANCE, "Relevant because you are pursuing higher education")
    if profile.get("studying") == "Yes":
        add("Education", db_config.STRONG_RELEVANCE, "Relevant because you are currently studying")
    if "homemaker" in occ:
        add("Women & Child", db_config.WEAK_RELEVANCE, "May be relevant for homemakers")
    if profile.get("bpl") == "Yes":
        add("Housing", db_config.WEAK_RELEVANCE, "May be relevant for BPL families")
        add("Healthcare", db_config.WEAK_RELEVANCE, "May be relevant for BPL families")
    if profile.get("minority") == "Yes":
        add("SC/ST/OBC Welfare", db_config.WEAK_RELEVANCE, "May be relevant for minority communities")
    if profile.get("gender") == "Female":
        add("Women & Child", db_config.WEAK_RELEVANCE, "May be relevant for women")
    income = profile.get("annual_income")
    if income is not None and income <= db_config.LOW_INCOME_HINT:
        add("Housing", db_config.WEAK_RELEVANCE, "May be relevant for low family income")
        add("Healthcare", db_config.WEAK_RELEVANCE, "May be relevant for low family income")
    return hints


def profile_signals(profile: dict) -> bool:
    return any(profile.get(k) not in (None, "") for k in
               ("occupation", "category", "gender", "annual_income", "education", "land_owner",
                "studying", "bpl", "minority", "disability", "residence"))


def relevance(rec: dict, profile: dict, conditions: list[dict]) -> tuple[int, list[str]]:
    score, reasons = 0, []
    hints = profile_categories(profile)
    for c in rec["categories"]:
        if c in hints:
            score += hints[c][0]
            reasons.append(hints[c][1])
    for c in conditions:
        if c["result"] == PASS and c["name"] in ("Occupation", "Social category", "Gender", "Income", "Education", "Land ownership",
                                                  "Residence", "BPL status", "Minority status", "Disability", "Ex-serviceman"):
            score += db_config.STRONG_RELEVANCE
            reasons.append(f"Your {c['name'].lower()} matches a scheme condition")
    return score, list(dict.fromkeys(reasons))


# -------------------------------------------------------------------- cards
def build_card(rec: dict, profile: dict) -> dict:
    res = evaluate(rec, profile)
    conds = res["conditions"]
    score, why = relevance(rec, profile, conds)
    official = rec["source_url"] or rec["official_url"] or ""
    income_text = rec["income_limit"] or (
        f"Up to ₹{int(rec['income_limit_annual']):,} per year" if rec["income_limit_annual"] is not None else None)
    short = rec["short_description"] or (rec["detailed_description"] or "")[:240] or None

    warnings = []
    if not rec["last_verified"]:
        warnings.append("This record has not been verified against the official source yet.")
    if rec["status"] != "active":
        warnings.append(f"Scheme status: {rec['status'].replace('_', ' ')} - confirm it is currently open.")

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
        "conditions": conds,
        "reasons": [f"{c['name']}: {c['reason']}" for c in conds if c["result"] != PASS or c["mandatory"]],
        "missing_fields": res["missing"],
        "missing_information": [MISSING_LABELS.get(f, f) for f in res["missing"]],
        "questions_for_user": [],
        "relevance": score,
        "relevance_reasons": why,
        "verification_warnings": warnings,
        "sources": [{
            "id": rec["id"], "file": rec.get("_file", "catalog"), "page": 0,
            "source_document": rec["source_document"], "official_url": official,
            "last_verified": rec["last_verified"] or "",
        }],
        "category": rec["category"],
        "categories": rec["categories"],
        "last_verified": rec["last_verified"],
        "official_url": rec["official_url"] or rec["source_url"],
        "source_url": rec["source_url"],
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


def select_cards(profile: dict, category=None, level=None, relevant_only=True) -> tuple[list[dict], int]:
    """Evaluate catalog schemes for this profile.
    Returns (cards to show, number of schemes evaluated). The SAME profile drives
    (1) which schemes are shown, (2) their order and (3) their eligibility status."""
    records = [r for r in load_catalog() if matches_filters(r, category, level, profile.get("state"))]
    cards = [build_card(r, profile) for r in records]
    evaluated = len(cards)
    if relevant_only and not category and profile_signals(profile):
        cards = [c for c in cards if c["relevance"] >= db_config.STRONG_RELEVANCE]
    cards.sort(key=lambda c: (STATUS_ORDER[c["status"]], -c["relevance"], c["scheme_name"]))
    return cards, evaluated