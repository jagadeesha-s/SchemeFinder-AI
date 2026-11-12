"""Agent 2 - Retrieval (RAG over ChromaDB)."""
import config
from backend.vector_store import SchemeVectorStore


class RetrievalAgent:
    def __init__(self, store: SchemeVectorStore) -> None:
        self.store = store

    def run(self, query: str, profile: dict | None = None, scheme_name: str | None = None) -> dict:
        """Return {'found', 'context', 'sources'} where sources maps 'S1' -> reference info."""
        profile = profile or {}
        parts = [scheme_name or "", query]
        hints = [str(profile[k]) for k in ("occupation", "category", "state", "education") if k in profile]
        search_text = " ".join(p for p in parts if p) + (" | applicant: " + ", ".join(hints) if hints else "")

        results = self.store.search(search_text, k=config.TOP_K)
        sources: dict[str, dict] = {}
        blocks: list[str] = []
        for i, (doc, score) in enumerate(results, start=1):
            sid = f"S{i}"
            m = doc.metadata
            page = m.get("page") or 0
            sources[sid] = {
                "id": sid,
                "file": m.get("source", "unknown"),
                "page": page,
                "scheme_name": m.get("scheme_name", ""),
                "department": m.get("department", ""),
                "official_url": m.get("official_url", ""),
                "excerpt": doc.page_content[:220].replace("\n", " "),
                "score": round(float(score), 3),
            }
            header = (
                f"[{sid}] Scheme: {m.get('scheme_name') or 'not specified'} | "
                f"Department: {m.get('department') or 'not specified'} | "
                f"File: {m.get('source')}{f', page {page}' if page else ''} | "
                f"Official URL: {m.get('official_url') or 'not specified'}"
            )
            blocks.append(f"{header}\n{doc.page_content}")

        return {"found": bool(results), "context": "\n\n---\n\n".join(blocks), "sources": sources}
