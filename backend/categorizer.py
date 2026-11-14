"""Keyword-based category suggestion. Only answers when there is enough evidence."""
import re

import db_config

KEYWORDS = {
    "Education": ["scholarship", "student", "tuition", "school", "college", "university", "education", "fellowship", "stipend"],
    "Agriculture": ["farmer", "agriculture", "crop", "irrigation", "cultivation", "kisan", "fertiliser", "livestock", "horticulture"],
    "Healthcare": ["health", "hospital", "medical", "treatment", "insurance cover", "maternal", "disease", "ayushman", "surgery"],
    "Housing": ["housing", "house", "awas", "shelter", "home loan", "pucca", "dwelling", "urban housing", "construction of house"],
    "Women & Child": ["women", "woman", "girl child", "pregnant", "lactating", "anganwadi", "maternity", "child", "mother"],
    "Employment": ["employment", "skill", "training", "wage", "job", "apprentice", "livelihood", "unemployed", "artisan"],
    "SC/ST/OBC Welfare": ["scheduled caste", "scheduled tribe", "backward class", "obc", "tribal", "dalit", "minority", "caste"],
    "Business": ["entrepreneur", "enterprise", "msme", "loan", "startup", "self-employment", "subsidy", "mudra", "business"],
}


def suggest_categories(text: str, min_hits: int = 3) -> list[str]:
    """Return up to 3 categories. A category needs >= min_hits DIFFERENT keywords in the text."""
    low = (text or "").lower()
    scores = {}
    for cat, words in KEYWORDS.items():
        hits = sum(1 for w in words if re.search(r"\b" + re.escape(w), low))
        if hits >= min_hits:
            scores[cat] = hits
    if not scores:
        return []
    top = max(scores.values())
    ranked = sorted((c for c, s in scores.items() if s >= 0.5 * top), key=lambda c: -scores[c])
    return [c for c in ranked if c in db_config.CATEGORIES][:3]