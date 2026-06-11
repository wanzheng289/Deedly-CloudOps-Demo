"""Load sampled EnterpriseRAG-Bench documents and optionally index them.

Default mode is dry-run: parse and chunk the JSONL file, then print summary.
Pass `--write` to persist parent chunks and vectors through the existing RAG
writer stack.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from project.backend.rag.jsonl_loader import EnterpriseRAGJsonlLoader


DEFAULT_INPUT = WORKSPACE_ROOT / "data" / "processed" / "enterprise_rag_bench" / "sample_documents.jsonl"


def summarize_chunks(chunks: list[dict]) -> dict:
    level_counts = Counter(str(chunk.get("chunk_level", "unknown")) for chunk in chunks)
    source_counts = Counter(str(chunk.get("source_type", "unknown")) for chunk in chunks)
    leaf_chunks = [chunk for chunk in chunks if int(chunk.get("chunk_level", 0) or 0) == 3]
    parent_chunks = [chunk for chunk in chunks if int(chunk.get("chunk_level", 0) or 0) in (1, 2)]
    return {
        "total_chunks": len(chunks),
        "parent_chunks": len(parent_chunks),
        "leaf_chunks": len(leaf_chunks),
        "level_counts": dict(sorted(level_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index sampled enterprise RAG documents.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--write", action="store_true", help="Actually write chunks to PostgreSQL/Milvus.")
    parser.add_argument("--batch-size", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    loader = EnterpriseRAGJsonlLoader()
    chunks = loader.load_jsonl(args.input)
    summary = summarize_chunks(chunks)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.write:
        print("Dry run only. Pass --write to write parent chunks and leaf vectors.")
        return

    from project.backend.db.postgres import init_db
    from project.backend.rag.indexer import MilvusWriter
    from project.backend.rag.parent_store import ParentChunkStore

    print("Initializing PostgreSQL tables...", flush=True)
    init_db()
    parent_docs = [chunk for chunk in chunks if int(chunk.get("chunk_level", 0) or 0) in (1, 2)]
    leaf_docs = [chunk for chunk in chunks if int(chunk.get("chunk_level", 0) or 0) == 3]

    print(f"Writing {len(parent_docs)} parent chunks to PostgreSQL...", flush=True)
    ParentChunkStore().upsert_documents(parent_docs)

    print(f"Writing {len(leaf_docs)} leaf chunks to Milvus with batch_size={args.batch_size}...", flush=True)

    def _progress(processed: int, total: int) -> None:
        percent = processed / total * 100 if total else 100
        print(f"Vector index progress: {processed}/{total} ({percent:.1f}%)", flush=True)

    MilvusWriter().write_documents(leaf_docs, batch_size=args.batch_size, progress_callback=_progress)
    print(f"Indexed {len(parent_docs)} parent chunks and {len(leaf_docs)} leaf chunks.")


if __name__ == "__main__":
    main()
