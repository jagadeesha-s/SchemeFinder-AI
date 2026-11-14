# SchemeFinder AI – Government Scheme Eligibility Navigator

Sign in with email OTP → browse all-India schemes by category → check eligibility → apply via official portals.
Agents: Intent Router → Retrieval (ChromaDB RAG) → Eligibility → Application → Explainer.

## Structure
```
app.py  config.py  requirements.txt  .env.example  .streamlit/config.toml
agents/    router, retrieval, eligibility, application, explainer
backend/   orchestrator, llm, vector_store, ingestion, catalog, auth, utils
ui/        styles.py, components.py, auth_page.py
prompts/   prompts.py
data/catalog/schemes.json   <- all-India scheme catalog (edit/extend this)
data/schemes/               <- official PDFs + sources.json
scripts/ingest.py
```

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp
python -m scripts.ingest        # builds ChromaDB from catalog + PDFs
streamlit run app.py
```

## .env
- `ANTHROPIC_API_KEY` – your Claude key.
- OTP email: set `SMTP_USER` and `SMTP_PASSWORD` (Gmail App Password: myaccount.google.com/apppasswords).
  Without SMTP and with `DEV_SHOW_OTP=true`, the OTP appears on screen (testing only).
- Change `APP_SECRET` to a long random string.

## Scheme catalog (`data/catalog/schemes.json`)
Each scheme has: scheme_name, department, level (Central/State), applicable_state, eligibility, income_limit,
benefits, required_documents, application_process, official_url, source_document, last_verified, deadline.
**All starter entries are unverified (`last_verified: null`).** Check each one on its official portal, correct it,
then set `last_verified` to the date. Fields not stated officially should stay `null` – the app then shows
"Not stated" and never invents values. Add state schemes by copying an entry with `"level": "State"`.
After editing, click **Re-index documents** (or run `python -m scripts.ingest`).

## Adding official PDFs
Put PDFs in `data/schemes/`, add an entry per file in `data/schemes/sources.json`, then re-index.

## Troubleshooting
- Login email not arriving: check SMTP settings / spam; use an App Password, not your Gmail password.
- "No documents indexed": click Re-index documents.
- Category filter returns nothing: the scheme needs a `category` (catalog entries have it; PDFs need it in sources.json).
- Model 404: set a valid `LLM_MODEL`. ModuleNotFoundError: activate `.venv`, run from project root.
- Reset accounts: delete `data/users.db`.
