"""Validate and normalise the user profile ONE time, so every agent sees the same clean values.

Privacy: we never ask for Aadhaar, bank account numbers or passwords. Sensitive questions are optional
and 'Prefer not to say' is accepted (it is simply not stored)."""
import re

import db_config

REQUIRED = ["age", "gender", "state", "category", "annual_income", "education", "occupation"]
LABELS = {
    "age": "Age", "gender": "Gender", "state": "State / UT", "district": "District", "residence": "Rural / Urban",
    "category": "Social category", "annual_income": "Annual family income", "family_size": "Family members",
    "education": "Highest education", "studying": "Currently studying", "course": "Course / degree",
    "study_year": "Year of study", "institution_type": "Institution type", "occupation": "Occupation",
    "disability": "Disability", "marital_status": "Marital status", "bpl": "BPL status",
    "minority": "Minority community", "minority_community": "Community", "ex_serviceman": "Ex-serviceman",
    "land_acres": "Landholding (acres)", "land_status": "Land ownership status", "irrigation": "Irrigation available",
    "business_type": "Business type", "business_age": "Business age (years)", "turnover": "Annual turnover (₹)",
    "employment_status": "Employment status", "skill_interest": "Skill-training interest", "land_owner": "Owns land",
}
GROUPS = {
    "Personal": ["age", "gender", "state", "district", "residence", "category", "annual_income", "family_size"],
    "Education": ["education", "studying", "course", "study_year", "institution_type"],
    "Occupation": ["occupation", "land_acres", "land_status", "irrigation", "business_type", "business_age",
                   "turnover", "employment_status", "skill_interest"],
    "Additional": ["disability", "marital_status", "bpl", "minority", "minority_community", "ex_serviceman"],
}
SENSITIVE = ("disability", "marital_status", "bpl", "minority", "ex_serviceman")

SOCIAL_ALIASES = {
    "general": "General", "gen": "General", "unreserved": "General", "open": "General",
    "obc": "OBC", "other backward class": "OBC", "other backward classes": "OBC",
    "sc": "SC", "scheduled caste": "SC", "scheduled castes": "SC", "dalit": "SC",
    "st": "ST", "scheduled tribe": "ST", "scheduled tribes": "ST", "tribal": "ST",
    "ews": "EWS", "economically weaker section": "EWS", "economically weaker sections": "EWS",
    "other": "Other",
}
GENDER_ALIASES = {
    "female": "Female", "woman": "Female", "women": "Female", "f": "Female", "girl": "Female",
    "male": "Male", "man": "Male", "m": "Male", "boy": "Male",
    "transgender": "Transgender", "third gender": "Transgender",
}
EDUCATION_RULES = [
    (r"phd|doctorate|doctoral", "Doctorate"),
    (r"(pursuing|studying|currently|student|year).*(post.?graduat|master|m\.?tech|m\.?sc|mba|m\.?a\b)", "Pursuing post-graduation"),
    (r"under.?graduate|(pursuing|studying|currently|student|\d(st|nd|rd|th) year|final year).*(graduat|degree|b\.?tech|b\.?e\b|engineering|bachelor|b\.?sc|b\.?com|b\.?a\b)|engineering student", "Pursuing graduation"),
    (r"post.?graduat|master|m\.?tech|m\.?sc|mba|m\.?com", "Post-graduate"),
    (r"graduat|bachelor|b\.?tech|b\.?e\b|b\.?sc|b\.?com|b\.?a\b|degree", "Graduate"),
    (r"diploma|\biti\b", "Diploma / ITI"),
    (r"12th|\bxii\b|\bpuc\b|higher secondary|intermediate|senior secondary", "12th pass"),
    (r"10th|\bsslc\b|matric|secondary school", "10th pass"),
    (r"primary|below 10|illiterate|no formal|\b[5-9]th\b|middle school", "Below 10th"),
]


def _blank(value) -> bool:
    return value is None or str(value).strip().lower() in ("", "none", "null", "select...", "nan", "prefer not to say")


def _choice(value, options) -> str | None:
    if _blank(value):
        return None
    low = str(value).strip().lower()
    return next((o for o in options if o.lower() == low), None)


def _number(value, lo, hi, as_int=False):
    if _blank(value):
        return None, None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None, "is not a number"
    if not lo <= num <= hi:
        return None, f"must be between {lo:g} and {hi:g}"
    return (int(num) if as_int else num), None


def normalize_education(text: str) -> str | None:
    if text in db_config.EDUCATION_OPTIONS:
        return text
    low = text.lower()
    for pattern, result in EDUCATION_RULES:
        if re.search(pattern, low):
            return result
    return None


def occupation_kind(occupation: str | None) -> str | None:
    occ = (occupation or "").lower()
    if "student" in occ:
        return "student"
    if "farmer" in occ or "agricultur" in occ or "cultivat" in occ:
        return "farmer"
    if "business" in occ or "self-employed" in occ or "self employed" in occ or "entrepreneur" in occ:
        return "business"
    if "unemploy" in occ or "jobless" in occ:
        return "unemployed"
    return None


def normalize_profile(raw: dict | None) -> tuple[dict, list[str]]:
    """Return (clean profile, warnings). Invalid values are dropped with a warning - never guessed.
    Fields that do not apply to the occupation (e.g. land for a student) are removed."""
    raw = raw or {}
    out, warnings = {}, []

    def num(key, label, lo, hi, as_int=False):
        value, err = _number(raw.get(key), lo, hi, as_int)
        if err:
            warnings.append(f"{label} {err} - ignored.")
        elif value is not None:
            out[key] = value

    num("age", "Age", 0, 120, True)
    num("annual_income", "Income", 0, 1e10)
    num("family_size", "Family members", 1, 30, True)

    if not _blank(raw.get("state")):
        match = _choice(raw["state"], db_config.INDIAN_STATES)
        if match:
            out["state"] = match
        else:
            warnings.append(f"State '{raw['state']}' was not recognised - ignored.")
    if not _blank(raw.get("category")):
        cat = SOCIAL_ALIASES.get(str(raw["category"]).strip().lower())
        if cat:
            out["category"] = cat
        else:
            warnings.append(f"Social category '{raw['category']}' was not recognised - ignored.")
    if not _blank(raw.get("gender")):
        gender = GENDER_ALIASES.get(str(raw["gender"]).strip().lower())
        if gender:
            out["gender"] = gender
        else:
            warnings.append(f"Gender '{raw['gender']}' was not recognised - ignored.")
    if not _blank(raw.get("education")):
        edu = normalize_education(str(raw["education"]).strip())
        if edu:
            out["education"] = edu
        else:
            warnings.append(f"Education '{raw['education']}' was not recognised - ignored. Pick an option from the list.")

    if not _blank(raw.get("occupation")):
        occ = str(raw["occupation"]).strip()[:80]
        out["occupation"] = next((o for o in db_config.OCCUPATION_TYPES if o.lower() == occ.lower()), occ)
    kind = occupation_kind(out.get("occupation"))

    if not _blank(raw.get("district")):
        out["district"] = str(raw["district"]).strip()[:60]
    for key, options in (("residence", db_config.RESIDENCE), ("marital_status", db_config.MARITAL),
                         ("disability", db_config.YES_NO), ("bpl", db_config.YES_NO),
                         ("minority", db_config.YES_NO), ("ex_serviceman", db_config.YES_NO),
                         ("studying", db_config.YES_NO)):
        value = _choice(raw.get(key), options)
        if value:
            out[key] = value
    if out.get("minority") == "Yes":
        community = _choice(raw.get("minority_community"), db_config.MINORITY_COMMUNITIES)
        if community:
            out["minority_community"] = community

    # ---- fields that depend on the occupation / studying
    if kind == "student":
        out["studying"] = "Yes"
    if out.get("studying") == "Yes":
        if not _blank(raw.get("course")):
            out["course"] = str(raw["course"]).strip()[:80]
        for key, options in (("study_year", db_config.STUDY_YEARS), ("institution_type", db_config.INSTITUTION_TYPES)):
            value = _choice(raw.get(key), options)
            if value:
                out[key] = value

    if kind == "farmer":
        num("land_acres", "Landholding", 0, 100000)
        for key, options in (("land_status", db_config.LAND_STATUS), ("irrigation", db_config.IRRIGATION)):
            value = _choice(raw.get(key), options)
            if value:
                out[key] = value
        status = out.get("land_status")
        if status == "Own land" and out.get("land_acres", 0) > 0:
            out["land_owner"] = "Yes"
        elif status == "Own land":
            warnings.append("You selected 'Own land' but the landholding is 0 acres - land ownership left unknown.")
        elif status == "Landless":
            out["land_owner"] = "No"
        else:                                    # tenant / sharecropper / not answered: do not guess
            land = _choice(raw.get("land_owner"), db_config.YES_NO)
            if land and not status:
                out["land_owner"] = land
    else:
        land = _choice(raw.get("land_owner"), db_config.YES_NO)
        if land:
            out["land_owner"] = land

    if kind == "business":
        if not _blank(raw.get("business_type")):
            out["business_type"] = str(raw["business_type"]).strip()[:60]
        num("business_age", "Business age", 0, 100)
        num("turnover", "Annual turnover", 0, 1e12)
    if kind == "unemployed":
        value = _choice(raw.get("employment_status"), db_config.EMPLOYMENT_STATUS)
        if value:
            out["employment_status"] = value
        value = _choice(raw.get("skill_interest"), db_config.YES_NO)
        if value:
            out["skill_interest"] = value
    return out, warnings


def missing_required(profile: dict) -> list[str]:
    return [LABELS[k] for k in REQUIRED if profile.get(k) in (None, "")]


def profile_completion(profile: dict) -> dict:
    """Percent of applicable (non-sensitive) fields answered."""
    kind = occupation_kind(profile.get("occupation"))
    fields = list(REQUIRED) + ["district", "residence", "family_size", "studying"]
    if profile.get("studying") == "Yes" or kind == "student":
        fields += ["course", "study_year", "institution_type"]
    if kind == "farmer":
        fields += ["land_acres", "land_status", "irrigation"]
    if kind == "business":
        fields += ["business_type", "business_age", "turnover"]
    if kind == "unemployed":
        fields += ["employment_status", "skill_interest"]
    done = [f for f in fields if profile.get(f) not in (None, "")]
    return {
        "percent": round(100 * len(done) / len(fields)),
        "missing_required": missing_required(profile),
        "missing_optional": [LABELS[f] for f in fields if f not in REQUIRED and profile.get(f) in (None, "")],
    }


def describe_profile(profile: dict) -> dict:
    """{group: [(label, value), ...]} for the read-only profile summary."""
    out = {}
    for group, keys in GROUPS.items():
        rows = []
        for k in keys:
            v = profile.get(k)
            if v in (None, ""):
                continue
            if k == "annual_income" or k == "turnover":
                v = f"₹{int(v):,}"
            rows.append((LABELS[k], v))
        if rows:
            out[group] = rows
    return out


def query_hints(profile: dict) -> list[str]:
    """Short phrases added to the semantic search so retrieval reflects the whole profile."""
    hints = []
    for key in ("occupation", "category", "gender", "state", "residence", "education", "course",
                "land_status", "business_type", "employment_status"):
        if profile.get(key):
            hints.append(f"{LABELS[key]}: {profile[key]}")
    if profile.get("studying") == "Yes":
        hints.append("currently studying")
    for key, text in (("bpl", "BPL family"), ("minority", "minority community"),
                      ("disability", "person with disability"), ("ex_serviceman", "ex-serviceman")):
        if profile.get(key) == "Yes":
            hints.append(text)
    return hints