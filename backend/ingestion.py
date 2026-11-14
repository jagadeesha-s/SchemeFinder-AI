"""Incremental ingestion: catalog JSON + PDF + TXT -> chunks -> ChromaDB.

How duplicates / updates are handled
  * every source (a catalog scheme, or a PDF/TXT file) gets a content hash stored in
    chroma_db/ingest_manifest.json
  * unchanged source  -> skipped (fast)
  * changed source    -> its old chunks are deleted, new chunks added
  * removed source    -> its chunks are deleted
  * chunk ids are  "<source key>::<number>", so repeating ingestion never creates duplicates
The ChromaDB collection is only wiped when you ask for a rebuild (or once, to migrate an old index)."""
import hashlib
import json
import os
import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

import config
import db_config
from backend.catalog import (flags, load_catalog_with_errors, make_metadata, record_hash,
                             record_metadata, record_text, reload_catalog)
from backend.categorizer import suggest_categories
from backend.vector_store import SchemeVectorStore

SUPPORTED = {".pdf", ".txt"}


# ----------------------------------------------------------------- helpers
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "scheme"


def load_manifest() -> dict:
    if db_config.MANIFEST_FILE.exists():
        try:
            data = json.loads(db_config.MANIFEST_FILE.read_text(encoding="utf-8"))
            if isinstance(data.get("sources"), dict):
                return data
        except Exception:
            pass
    return {"version": 1, "sources": {}}


def save_manifest(manifest: dict) -> None:
    db_config.MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_config.MANIFEST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    os.replace(tmp, db_config.MANIFEST_FILE)


def index_summary() -> dict:
    """Unique schemes (not chunks) according to the manifest."""
    sources = load_manifest()["sources"]
    schemes = {sid for s in sources.values() for sid in s.get("scheme_ids", [])}
    return {"schemes": len(schemes), "sources": len(sources),
            "chunks": sum(len(s.get("ids", [])) for s in sources.values())}


def load_sources_metadata() -> dict:
    """data/schemes/sources.json: file name -> scheme_name, department, official_url, category,
    additional_categories, level, applicable_state, source_document, last_verified, id, status."""
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


# ------------------------------------------------------------ chunk builders
def _catalog_chunks(rec: dict, splitter) -> tuple[list[Document], list[str], list[str], list[str]]:
    parts = splitter.split_text(record_text(rec)) or [record_text(rec)]
    meta = record_metadata(rec)
    docs, ids = [], []
    for i, part in enumerate(parts):
        if i > 0:
            part = f"Scheme: {rec['scheme_name']}\n{part}"
        docs.append(Document(page_content=part, metadata=dict(meta)))
        ids.append(f"catalog:{rec['id']}::{i}")
    return docs, ids, [rec["id"]], []


def _file_chunks(path: Path, rel: str, entry: dict, splitter) -> tuple[list[Document], list[str], list[str], list[str]]:
    pages = load_pdf(path) if path.suffix.lower() == ".pdf" else load_txt(path)
    if not pages:
        raise ValueError("no extractable text (scanned PDF? use a text-based PDF)")
    warnings = []
    full_text = "\n".join(p.page_content for p in pages)

    name = entry.get("scheme_name")
    if not name:
        first = next((ln.strip() for ln in full_text.splitlines() if ln.strip()), path.stem)
        name = first[:120]
        warnings.append(f"{rel}: scheme name guessed from the first line - add it in sources.json")

    primary = entry.get("category")
    extra = list(entry.get("additional_categories") or [])
    if not primary:
        guessed = suggest_categories(full_text[:8000])
        if guessed:
            primary, extra = guessed[0], guessed[1:]
            warnings.append(f"{rel}: category auto-detected as {guessed} (not verified)")
        else:
            warnings.append(f"{rel}: category unknown - add it in sources.json")
    categories = list(dict.fromkeys(([primary] if primary else []) + extra))

    scheme_id = entry.get("id") or _slug(path.stem)
    meta = make_metadata(
        scheme_id=scheme_id, scheme_name=name, categories=categories, level=entry.get("level"),
        state=entry.get("applicable_state"), department=entry.get("department"),
        official_url=entry.get("official_url"), source_url=entry.get("source_url"),
        source_document=entry.get("source_document") or path.name,
        last_verified=entry.get("last_verified"), status=entry.get("status"),
        doc_type=path.suffix.lower().lstrip("."), source=path.name,
    )
    docs, ids, seen = [], [], set()
    for chunk in splitter.split_documents(pages):
        digest = _sha(chunk.page_content.encode())
        if digest in seen:          # identical chunk inside the same file
            continue
        seen.add(digest)
        chunk.metadata = {**meta, "page": chunk.metadata.get("page", 0)}
        docs.append(chunk)
        ids.append(f"file:{rel}::{len(ids)}")
    return docs, ids, [scheme_id], warnings


# -------------------------------------------------------------------- main
def ingest_directory(store: SchemeVectorStore, reset: bool = False, progress=None) -> dict:
    """Incremental by default. reset=True wipes and rebuilds the collection.
    progress(done, total, message) is optional (used by the Streamlit progress bar)."""
    notify = progress or (lambda done, total, msg: None)
    stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0,
             "errors": [], "warnings": [], "migrated": False}

    manifest = load_manifest()
    if reset:
        store.reset()
        manifest = {"version": 1, "sources": {}}
    elif not manifest["sources"] and store.count() > 0:
        # Index made by the older version of the project: rebuild once to avoid duplicates.
        store.reset()
        stats["migrated"] = True
        stats["warnings"].append("An older index (without a manifest) was found and rebuilt once.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)
    catalog_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=100)

    # ---- collect every source
    reload_catalog()
    records, cat_errors, failed_files = load_catalog_with_errors()
    stats["errors"] += cat_errors
    units = [{"key": f"catalog:{r['id']}", "label": r["scheme_name"], "hash": record_hash(r),
              "build": (lambda r=r: _catalog_chunks(r, catalog_splitter))} for r in records]

    sources_meta = load_sources_metadata()
    config.SCHEMES_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(p for p in config.SCHEMES_DIR.rglob("*") if p.suffix.lower() in SUPPORTED):
        rel = path.relative_to(config.SCHEMES_DIR).as_posix()
        entry = sources_meta.get(path.name, {})
        digest = _sha(path.read_bytes() + json.dumps(entry, sort_keys=True).encode())
        units.append({"key": f"file:{rel}", "label": rel, "hash": digest,
                      "build": (lambda p=path, r=rel, e=entry: _file_chunks(p, r, e, splitter))})

    # ---- add / update
    total = len(units)
    try:
        for n, unit in enumerate(units, start=1):
            notify(n - 1, total, f"Checking {unit['label']}")
            old = manifest["sources"].get(unit["key"])
            if old and old["hash"] == unit["hash"]:
                stats["unchanged"] += 1
                continue
            try:
                docs, ids, scheme_ids, warns = unit["build"]()
                if old:
                    store.delete(old["ids"])
                try:
                    store.add_documents(docs, ids)
                except Exception:
                    manifest["sources"].pop(unit["key"], None)
                    raise
                manifest["sources"][unit["key"]] = {
                    "hash": unit["hash"], "ids": ids, "scheme_ids": scheme_ids,
                }
                stats["updated" if old else "added"] += 1
                stats["warnings"] += warns
            except Exception as exc:
                stats["errors"].append(f"{unit['label']}: {exc}")

        # ---- remove sources that disappeared (never when a catalog file failed to load)
        current = {u["key"] for u in units}
        for key in list(manifest["sources"]):
            if key in current:
                continue
            if key.startswith("catalog:") and failed_files:
                stats["warnings"].append(f"Kept {key} because a catalog file failed to load.")
                continue
            store.delete(manifest["sources"][key]["ids"])
            del manifest["sources"][key]
            stats["removed"] += 1
    finally:
        save_manifest(manifest)

    notify(total, total, "Done")
    summary = index_summary()
    stats["unique_schemes"] = summary["schemes"]
    stats["chunks"] = store.count()
    stats["files"] = summary["sources"]
    stats["skipped"] = stats["errors"]   # old key name, kept for compatibility
    return stats