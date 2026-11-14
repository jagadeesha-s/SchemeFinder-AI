"""Run from the project root:
    python -m scripts.ingest              (incremental - only new/changed sources)
    python -m scripts.ingest --rebuild    (wipe the collection and rebuild everything)"""
import argparse

from backend.ingestion import ingest_directory
from backend.vector_store import SchemeVectorStore


def show(done: int, total: int, message: str) -> None:
    print(f"[{done}/{total}] {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="wipe and rebuild the whole index")
    args = parser.parse_args()

    print("Loading embedding model and ChromaDB ...")
    store = SchemeVectorStore()
    stats = ingest_directory(store, reset=args.rebuild, progress=show)

    print("\n=== Ingestion report ===")
    print(f"Unique schemes indexed : {stats['unique_schemes']}")
    print(f"Chunks in ChromaDB     : {stats['chunks']}")
    print(f"Added {stats['added']} | Updated {stats['updated']} | Unchanged {stats['unchanged']} | Removed {stats['removed']}")
    for w in stats["warnings"]:
        print("WARNING:", w)
    for e in stats["errors"]:
        print("ERROR  :", e)


if __name__ == "__main__":
    main()