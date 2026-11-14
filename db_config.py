"""Extra settings for the scheme-database expansion.
Kept in a separate file so your existing config.py (and your Gemini settings) stay untouched."""
import os

import config

CATALOG_DIR = config.BASE_DIR / "data" / "catalog"
MANIFEST_FILE = config.CHROMA_DIR / "ingest_manifest.json"

CATEGORIES = [
    "Education", "Agriculture", "Healthcare", "Housing",
    "Women & Child", "Employment", "SC/ST/OBC Welfare", "Business",
]
# Chroma cannot search inside lists, so every category becomes its own True/False field: cat_<slug>
CATEGORY_SLUGS = {
    "Education": "education", "Agriculture": "agriculture", "Healthcare": "healthcare",
    "Housing": "housing", "Women & Child": "women_child", "Employment": "employment",
    "SC/ST/OBC Welfare": "welfare", "Business": "business",
}
LEVELS = ["Central", "State", "UT"]
STATUSES = ["active", "closed", "discontinued", "verification_required"]
SOCIAL_CATEGORIES = ["General", "OBC", "SC", "ST", "EWS", "Other"]
EDUCATION_ORDER = [
    "Below 10th", "10th pass", "12th pass", "Diploma / ITI", "Graduate", "Post-graduate", "Doctorate",
]
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".ac.in", ".edu.in")

# Performance switches
USE_LLM_EXPLAINER = os.getenv("USE_LLM_EXPLAINER", "true").lower() == "true"
MAX_BROWSE_RESULTS = 200       # safety cap for category browsing
CARDS_PER_PAGE = 20            # cards drawn before "Show more"