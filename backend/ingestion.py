"""PDF / text ingestion: load -> extract -> chunk -> embed -> store in ChromaDB."""
import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

import config
from backend.vector_store import SchemeVectorStore

SUPPORTED = {".pdf", ".txt"}


def load_sources_metadata() -> dict:
    """data/schemes/sources.json maps file name -> scheme_name, department, official_url."""
    if config.SOURCES_FILE.exists():
        try:
            data = json.loads(config.SOURCES_FILE.read_text(encoding="utf-8"))
            return {k: v for k, v in data.items() if not k.startswith("_")}
        except json.JSONDecodeError:
            print("WARNING: sources.json is not valid JSON; ignoring it.")
    return {}


def load_pdf(path: Path) -> list[Document]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(Document(page_content=text, metadata={"page": number}))
    return pages


def load_txt(path: Path) -> list[Document]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    return [Document(page_content=text, metadata={"page": 0})] if text else []


def ingest_directory(store: SchemeVectorStore, reset: bool = True) -> dict:
    files = sorted(p for p in config.SCHEMES_DIR.rglob("*") if p.suffix.lower() in SUPPORTED)
    sources_meta = load_sources_metadata()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )
    if reset:
        store.reset()

    stats = {"files": 0, "chunks": 0, "skipped": []}
    for path in files:
        try:
            pages = load_pdf(path) if path.suffix.lower() == ".pdf" else load_txt(path)
        except Exception as exc:
            stats["skipped"].append(f"{path.name} (error: {exc})")
            continue
        if not pages:
            stats["skipped"].append(f"{path.name} (no extractable text - scanned PDF?)")
            continue

        meta = sources_meta.get(path.name, {})
        chunks = splitter.split_documents(pages)
        ids = []
        for i, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "source": path.name,
                    "scheme_name": meta.get("scheme_name", ""),
                    "department": meta.get("department", ""),
                    "official_url": meta.get("official_url", ""),
                }
            )
            ids.append(f"{path.name}-{i}")
        store.add_documents(chunks, ids)
        stats["files"] += 1
        stats["chunks"] += len(chunks)
    return stats
