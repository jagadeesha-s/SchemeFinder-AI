"""Agent 2 - Retrieval (RAG over ChromaDB with metadata filters)."""
import config
from backend.catalog import find_scheme
from backend.vector_store import SchemeVectorStore


class RetrievalAgent:
    def __init__(self, store: SchemeVectorStore) -> None:
        self.store = store

    def run(self, query: str, profile: dict | None = None, scheme_name: str | None = None,
            category: str | None = None, level: str | None = None) -> dict:
        """Returns:
          catalog_ids - ids of catalog schemes found (checked later by the rule engine, no LLM needed)
          context/sources - only PDF/TXT chunks (these still need the LLM eligibility agent)"""
        profile = profile or {}
        hints = [str(profile[k]) for k in ("occupation", "category", "state", "education") if k in profile]
        search_text = " ".join(p for p in (scheme_name or "", query) if p)
        if hints:
            search_text += " | applicant: " + ", ".join(hints)

        flt = self.store.make_filter(category=category, level=level, state=profile.get("state"))
        results = self.store.search(search_text, k=config.TOP_K, flt=flt)

        catalog_ids: list[str] = []
        if scheme_name:                      # user named a scheme: make sure it is included
            rec = find_scheme(scheme_name)
            if rec:
                catalog_ids.append(rec["id"])

        sources: dict[str, dict] = {}
        blocks: list[str] = []
        for doc, score in results:
            m = doc.metadata
            if m.get("doc_type") == "catalog" and m.get("scheme_id"):
                if m["scheme_id"] not in catalog_ids:
                    catalog_ids.append(m["scheme_id"])
                continue
            sid = f"S{len(sources) + 1}"
            page = m.get("page") or 0
            sources[sid] = {
                "id": sid, "file": m.get("source", "unknown"), "page": page,
                "scheme_name": m.get("scheme_name", ""), "department": m.get("department", ""),
                "official_url": m.get("official_url", "") or m.get("source_url", ""),
                "category": m.get("category", ""), "level": m.get("level", ""),
                "state": m.get("state", ""), "last_verified": m.get("last_verified", ""),
                "source_document": m.get("source_document", ""),
                "excerpt": doc.page_content[:220].replace("\n", " "), "score": round(float(score), 3),
            }
            blocks.append(
                f"[{sid}] Scheme: {m.get('scheme_name') or 'not specified'} | "
                f"Category: {m.get('category') or 'not specified'} | Level: {m.get('level') or 'not specified'} | "
                f"Applicable state: {m.get('state') or 'not specified'} | "
                f"Department: {m.get('department') or 'not specified'} | "
                f"Last verified: {m.get('last_verified') or 'not yet verified'} | "
                f"File: {m.get('source')}{f', page {page}' if page else ''} | "
                f"Official URL: {m.get('official_url') or 'not specified'}\n{doc.page_content}"
            )

        return {
            "found": bool(catalog_ids or sources),
            "catalog_ids": catalog_ids,
            "context": "\n\n---\n\n".join(blocks),
            "sources": sources,
        }