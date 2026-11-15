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
# Options shown in the profile form. "Pursuing ..." options are counted as the level already completed.
EDUCATION_OPTIONS = EDUCATION_ORDER + ["Pursuing graduation", "Pursuing post-graduation"]
EDUCATION_EQUIV = {"Pursuing graduation": "12th pass", "Pursuing post-graduation": "Graduate"}
GENDERS = ["Female", "Male", "Transgender"]
LAND_OPTIONS = ["Yes", "No"]
INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]
# ---- profile form options
OCCUPATION_TYPES = ["Student", "Farmer", "Unemployed", "Private employee", "Government employee",
                    "Self-employed", "Business owner", "Homemaker", "Other"]
RESIDENCE = ["Rural", "Urban"]
STUDY_YEARS = ["1st year", "2nd year", "3rd year", "4th year", "5th year or higher"]
INSTITUTION_TYPES = ["Government college", "Government-aided college", "Private college", "University",
                     "ITI / Polytechnic", "School", "Other"]
MARITAL = ["Single", "Married", "Widowed", "Divorced / Separated"]
YES_NO = ["Yes", "No"]
MINORITY_COMMUNITIES = ["Muslim", "Christian", "Sikh", "Buddhist", "Jain", "Parsi (Zoroastrian)"]
LAND_STATUS = ["Own land", "Tenant / leased", "Sharecropper", "Landless"]
IRRIGATION = ["Yes", "Partial", "No"]
BUSINESS_TYPES = ["Manufacturing", "Trading / retail", "Services", "Food / agriculture-based",
                  "Handicraft / artisan", "Other"]
EMPLOYMENT_STATUS = ["Looking for work", "Not looking for work", "Recently lost job", "Never employed"]

# Relevance (ranking/selection only - NEVER used to decide eligibility)
STRONG_RELEVANCE = 2
WEAK_RELEVANCE = 1
LOW_INCOME_HINT = 300000       # used only to rank housing/health schemes a little higher
CATEGORY_BOOST = {"strong": 0.15, "weak": 0.05}   # added to the similarity score when re-ranking

OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".ac.in", ".edu.in")

# Performance switches
USE_LLM_EXPLAINER = os.getenv("USE_LLM_EXPLAINER", "true").lower() == "true"
MAX_BROWSE_RESULTS = 200       # safety cap for category browsing
CARDS_PER_PAGE = 20            # cards drawn before "Show more"