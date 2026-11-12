
"""Central configuration for SchemeFinder AI."""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ---- Project paths --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# Load local .env file (for running on your computer)
load_dotenv(BASE_DIR / ".env")


# ---- Streamlit Secrets ----------------------------------------------

def get_secret(name, default=""):
    """Safely read secrets from Streamlit Cloud."""
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


# ---- Gemini LLM -----------------------------------------------------

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY", "").strip()
    or get_secret("GEMINI_API_KEY")
)

LLM_MODEL = (
    os.getenv("LLM_MODEL", "").strip()
    or get_secret("LLM_MODEL", "gemini-3.5-flash-lite")
)

LLM_MAX_TOKENS = 4096


# ---- Embeddings / Vector DB -----------------------------------------

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)

CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "government_schemes"


# ---- Documents ------------------------------------------------------

SCHEMES_DIR = BASE_DIR / "data" / "schemes"
SOURCES_FILE = SCHEMES_DIR / "sources.json"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


# ---- Retrieval ------------------------------------------------------

TOP_K = 8
MIN_RELEVANCE_SCORE = 0.2


# ---- Profile --------------------------------------------------------

REQUIRED_PROFILE_FIELDS = [
    "age",
    "state",
    "annual_income",
    "category",
    "occupation",
    "education"
]

PROFILE_KEYS = REQUIRED_PROFILE_FIELDS + ["gender"]


FIELD_QUESTIONS = {
    "age": "What is your age?",
    "state": "Which state or Union Territory do you live in?",
    "annual_income": "What is your total annual family income (in ₹)?",
    "category": "Which category do you belong to (General, OBC, SC, ST, EWS)?",
    "occupation": "What is your occupation?",
    "education": "What is your highest level of education?",
}


# ---- Disclaimer -----------------------------------------------------

DISCLAIMER = (
    "SchemeFinder AI gives guidance based only on the official documents "
    "you have indexed. It does not approve applications. Always confirm "
    "eligibility, deadlines and links on the official government portal "
    "before applying."
)
