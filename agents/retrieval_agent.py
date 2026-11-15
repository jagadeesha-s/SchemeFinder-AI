"""Agent 2 - Retrieval (RAG over ChromaDB).

How the profile is used here
  1. state + category/level filters  -> ChromaDB metadata filter (central schemes OR the user's state)
  2. profile text                    -> appended to the semantic query
  3. profile -> relevant categories  -> re-rank: matching categories get a small score boost
  4. one chunk per catalog scheme, at most 2 chunks per document scheme -> no duplicate results"""
import config
import db_config
from backend.catalog import find_scheme
from backend.profile import query_hints
from backend.rules import profile_categories
from backend.vector_store import SchemeVectorStore

MAX_CHUNKS_PER_DOC_SCHEME = 2


class RetrievalAgent:
    def __init__(self, store: SchemeVectorStore) -> None:
        self.store = store

    def run(self, query: str, profile: dict | None = None, scheme_name: str | None = None,
            category: str | None = None, level: str | None = None) -> dict:
        profile = profile or {}
        hints = query_hints(profile)     # occupation, category, gender, state, residence, studying, BPL ...
        search_text = " ".join(p for p in (scheme_name or "", query) if p)
        if hints:
            search_text += " | applicant " + ", ".join(hints)

        flt = self.store.make_filter(category=category, level=level, state=profile.get("state"))
        results = self.store.search(search_text, k=config.TOP_K * 2, flt=flt)   # fetch extra, then re-rank

        # ---- re-rank with the profile (selection/ranking only, never eligibility)
        hints_by_cat = profile_categories(profile)
        ranked = []
        for doc, score in results:
            boost = 0.0
            for cat, (weight, _) in hints_by_cat.items():
                slug = db_config.CATEGORY_SLUGS.get(cat)
                if slug and doc.metadata.get(f"cat_{slug}"):
                    key = "strong" if weight >= db_config.STRONG_RELEVANCE else "weak"
                    boost = max(boost, db_config.CATEGORY_BOOST[key])
            ranked.append((score + boost, score, doc))
        ranked.sort(key=lambda t: -t[0])

        catalog_ids: list[str] = []
        if scheme_name:                       # user named a scheme: make sure it is included
            rec = find_scheme(scheme_name)
            if rec:
                catalog_ids.append(rec["id"])

        sources: dict[str, dict] = {}
        blocks: list[str] = []
        per_scheme: dict[str, int] = {}
        for _, score, doc in ranked:
            if len(catalog_ids) + len(sources) >= config.TOP_K:
                break
            m = doc.metadata
            sid_key = m.get("scheme_id") or m.get("source", "")
            if m.get("doc_type") == "catalog" and m.get("scheme_id"):
                if m["scheme_id"] not in catalog_ids:
                    catalog_ids.append(m["scheme_id"])
                continue
            if per_scheme.get(sid_key, 0) >= MAX_CHUNKS_PER_DOC_SCHEME:
                continue
            per_scheme[sid_key] = per_scheme.get(sid_key, 0) + 1
            sid = f"S{len(sources) + 1}"
            page = m.get("page") or 0
            sources[sid] = {
                "id": sid, "file": m.get("source", "unknown"), "page": page,
                "scheme_name": m.get("scheme_name", ""), "department": m.get("department", ""),
                "official_url": m.get("official_url", "") or m.get("source_url", ""),
                "category": m.get("category", ""), "level": m.get("level", ""),
                "state": m.get("state", ""), "status": m.get("status", ""),
                "last_verified": m.get("last_verified", ""),
                "source_document": m.get("source_document", ""),
                "excerpt": doc.page_content[:220].replace("\n", " "), "score": round(float(score), 3),
            }
            blocks.append(
                f"[{sid}] Scheme: {m.get('scheme_name') or 'not specified'} | "
                f"Category: {m.get('category') or 'not specified'} | Level: {m.get('level') or 'not specified'} | "
                f"Applicable state: {m.get('state') or 'not specified'} | "
                f"Department: {m.get('department') or 'not specified'} | "
                f"Status: {m.get('status') or 'not specified'} | "
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