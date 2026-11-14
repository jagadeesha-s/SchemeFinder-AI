"""ChromaDB setup + embeddings (cached) + metadata filters + small query cache."""
import json
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

import config
import db_config


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Loaded once per process and shared."""
    return HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


class SchemeVectorStore:
    def __init__(self) -> None:
        self.embeddings = get_embeddings()
        self.version = 0          # increases whenever the index changes (used by caches)
        self._cache: dict = {}
        self.db = self._connect()

    def _connect(self) -> Chroma:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        return Chroma(
            collection_name=config.COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=str(config.CHROMA_DIR),
            collection_metadata={"hnsw:space": "cosine"},
        )

    def _changed(self) -> None:
        self.version += 1
        self._cache.clear()

    # ------------------------------------------------------------ write
    def add_documents(self, docs: list[Document], ids: list[str]) -> None:
        if docs:
            self.db.add_documents(docs, ids=ids)
            self._changed()

    def delete(self, ids: list[str]) -> None:
        for i in range(0, len(ids), 500):
            self.db.delete(ids=ids[i:i + 500])
        if ids:
            self._changed()

    def reset(self) -> None:
        try:
            self.db.delete_collection()
        except Exception:
            pass
        self.db = self._connect()
        self._changed()

    # ------------------------------------------------------------- read
    @staticmethod
    def make_filter(category: str | None = None, level: str | None = None, state: str | None = None):
        """Build a ChromaDB metadata filter (returns None when nothing to filter)."""
        conds = []
        slug = db_config.CATEGORY_SLUGS.get(category or "")
        if slug:
            conds.append({f"cat_{slug}": True})
        if level == "Central":
            conds.append({"is_central": True})
        elif level in ("State", "UT", "State/UT"):
            conds.append({"is_central": False})
        if state:
            conds.append({"$or": [{"is_central": True}, {"state": state}, {"level": "Unknown"}]})
        if not conds:
            return None
        return conds[0] if len(conds) == 1 else {"$and": conds}

    def search(self, query: str, k: int = config.TOP_K, flt: dict | None = None) -> list[tuple[Document, float]]:
        key = (query, k, json.dumps(flt, sort_keys=True), self.version)
        if key in self._cache:
            return self._cache[key]
        results = self.db.similarity_search_with_relevance_scores(query, k=k, filter=flt)
        results = [(d, s) for d, s in results if s >= config.MIN_RELEVANCE_SCORE]
        if len(self._cache) > 128:
            self._cache.clear()
        self._cache[key] = results
        return results

    def count(self) -> int:
        try:
            return self.db._collection.count()
        except Exception:
            return 0