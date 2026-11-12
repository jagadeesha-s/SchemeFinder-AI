"""Run from the project root:  python -m scripts.ingest"""
from backend.ingestion import ingest_directory
from backend.vector_store import SchemeVectorStore


def main() -> None:
    print("Loading embedding model and ChromaDB ...")
    store = SchemeVectorStore()
    stats = ingest_directory(store, reset=True)
    print(f"Indexed {stats['files']} file(s) into {stats['chunks']} chunk(s).")
    for item in stats["skipped"]:
        print("Skipped:", item)


if __name__ == "__main__":
    main()
