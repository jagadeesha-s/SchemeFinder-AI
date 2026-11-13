# SchemeFinder AI – Government Scheme Eligibility Navigator

Live Website: https://schemefinder-ai.streamlit.app/

Find Indian government schemes and check your eligibility using AI.
Multi-agent RAG app: Intent Router → Retrieval → Eligibility → Application → Explainer.
Stack: Streamlit, LangChain, gemini API, ChromaDB, HuggingFace embeddings, pypdf.

## Folder structure
```
schemefinder-ai/
├── app.py                  # Streamlit frontend
├── config.py               # settings
├── requirements.txt  .env.example  .gitignore
├── agents/                 # router, retrieval, eligibility, application, explainer
├── backend/                # orchestrator, llm, vector_store (ChromaDB), ingestion, utils
├── prompts/prompts.py      # all LangChain prompts
├── scripts/ingest.py       # CLI indexing
├── data/schemes/           # put official PDFs here + sources.json
└── chroma_db/              # vector DB (auto-created)
```

## Setup (VS Code terminal, Python 3.10–3.12)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```
Edit `.env` and set `ANTHROPIC_API_KEY` (from console.anthropic.com). Change `LLM_MODEL` if needed.
In VS Code: Ctrl+Shift+P → "Python: Select Interpreter" → choose `.venv`.

## Add official scheme documents
1. Download official PDFs from government sites (e.g. pmkisan.gov.in, pmjay.gov.in, india.gov.in, myscheme.gov.in) into `data/schemes/`.
2. Add one entry per file in `data/schemes/sources.json` (scheme_name, department, official_url). Links shown in the app come only from here or from the document text.
3. Delete the two `*_sample.txt` files (testing only) once you have real PDFs.
4. Index: `python -m scripts.ingest` (or press **Re-index documents** in the app).
Scanned (image-only) PDFs have no extractable text; use text-based PDFs.

## Run
```bash
streamlit run app.py
```
Opens at http://localhost:8501. The first run downloads the embedding model (~90 MB).

## Sample queries
| Query | Expected behaviour |
|---|---|
| "I am a 40-year-old farmer from Bihar. What schemes can I get?" | Cards for matching schemes; PM-KISAN "potentially eligible" (land ownership / tax status not confirmed) with follow-up questions |
| "Am I eligible for PM-KISAN? I pay income tax." | PM-KISAN marked **Not eligible**, citing the income-tax exclusion and source |
| "How do I apply for Ayushman Bharat?" | Application Guidance with documents/steps found in the docs, official portal link, deadline "Not verified" |
| "Scholarship for astronaut training" | Clear "no matching scheme found" message |

## Troubleshooting
- **ANTHROPIC_API_KEY not found** – `.env` must be in the project root; restart Streamlit.
- **Model not found / 404** – set a valid `LLM_MODEL` in `.env`.
- **No documents indexed** – put files in `data/schemes/`, click Re-index.
- **ModuleNotFoundError** – activate `.venv`, rerun `pip install -r requirements.txt`; run commands from the project root.
- **Chroma errors after upgrading** – delete the contents of `chroma_db/` and re-index.
- **Empty results** – PDF may be scanned; lower `MIN_RELEVANCE_SCORE` in `config.py`.
- **Slow first start** – embedding model download; later runs are cached.
