"""ChromaDB setup + embeddings."""
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

import config


class SchemeVectorStore:
    def __init__(self) -> None:
        self.embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL,
            encode_kwargs={"normalize_embeddings": True},
        )
        self.db = self._connect()

    def _connect(self) -> Chroma:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        return Chroma(
            collection_name=config.COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=str(config.CHROMA_DIR),
            collection_metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, docs: list[Document], ids: list[str]) -> None:
        if docs:
            self.db.add_documents(docs, ids=ids)

    def search(self, query: str, k: int = config.TOP_K) -> list[tuple[Document, float]]:
        results = self.db.similarity_search_with_relevance_scores(query, k=k)
        return [(d, s) for d, s in results if s >= config.MIN_RELEVANCE_SCORE]

    def count(self) -> int:
        try:
            return self.db._collection.count()
        except Exception:
            return 0

    def reset(self) -> None:
        try:
            self.db.delete_collection()
        except Exception:
            pass
        self.db = self._connect()
