"""Central configuration for SchemeFinder AI."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ---- LLM -------------------------------------------------------------


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "gemini-3.5-flash-lite"
)
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 4096
# ---- Embeddings / Vector DB -----------------------------------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "government_schemes"

# ---- Documents -------------------------------------------------------
SCHEMES_DIR = BASE_DIR / "data" / "schemes"
SOURCES_FILE = SCHEMES_DIR / "sources.json"
CATALOG_FILE = BASE_DIR / "data" / "catalog" / "schemes.json"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# ---- Retrieval -------------------------------------------------------
TOP_K = 8
MIN_RELEVANCE_SCORE = 0.2  # cosine-based relevance, 0..1

# ---- Profile ---------------------------------------------------------
REQUIRED_PROFILE_FIELDS = ["age", "state", "annual_income", "category", "occupation", "education"]
PROFILE_KEYS = REQUIRED_PROFILE_FIELDS + ["gender"]

FIELD_QUESTIONS = {
    "age": "What is your age?",
    "state": "Which state or Union Territory do you live in?",
    "annual_income": "What is your total annual family income (in ₹)?",
    "category": "Which category do you belong to (General, OBC, SC, ST, EWS)?",
    "occupation": "What is your occupation?",
    "education": "What is your highest level of education?",
}

DISCLAIMER = (
    "SchemeFinder AI gives guidance based only on the official documents you have indexed. "
    "It does not approve applications. Always confirm eligibility, deadlines and links on the "
    "official government portal before applying."
)

# ---- Categories shown in the UI --------------------------------------
CATEGORIES = [
    "Education", "Agriculture", "Healthcare", "Housing",
    "Women & Child", "Employment", "SC/ST/OBC Welfare", "Business",
]

# ---- Login / OTP -----------------------------------------------------
USERS_DB = BASE_DIR / "data" / "users.db"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
SMTP_CONFIGURED = bool(SMTP_USER and SMTP_PASSWORD)
DEV_SHOW_OTP = os.getenv("DEV_SHOW_OTP", "true").lower() == "true"
APP_SECRET = os.getenv("APP_SECRET", "change-me")
OTP_LENGTH = 6
OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_SECONDS = 45
OTP_MAX_ATTEMPTS = 5
