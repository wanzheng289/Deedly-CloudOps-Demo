"""JSONL loaders for enterprise RAG corpora."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

class EnterpriseRAGJsonlLoader:
    """Load normalized EnterpriseRAG-Bench JSONL documents into RAG chunks.

    Expected input rows are produced by
    `data_pipelines/enterprise_rag_bench/sample_documents.py`.
    """

    def __init__(
        self,
        level_1_size: int = 1200,
        level_1_overlap: int = 240,
        level_2_size: int = 600,
        level_2_overlap: int = 120,
        level_3_size: int = 300,
        level_3_overlap: int = 60,
    ):
        self.levels = {
            1: (level_1_size, level_1_overlap),
            2: (level_2_size, level_2_overlap),
            3: (level_3_size, level_3_overlap),
        }

    @staticmethod
    def _build_chunk_id(doc_id: str, level: int, index: int) -> str:
        return f"{doc_id}::l{level}::{index}"

    @staticmethod
    def _sliding_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
        clean = (text or "").strip()
        if not clean:
            return []
        chunks: list[str] = []
        start = 0
        step = max(1, chunk_size - overlap)
        while start < len(clean):
            chunk = clean[start : start + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
            if start + chunk_size >= len(clean):
                break
            start += step
        return chunks

    def load_jsonl(self, file_path: str | Path, filename: str | None = None) -> list[dict]:
        path = Path(file_path)
        source_filename = filename or path.name
        documents: list[dict] = []
        global_chunk_idx = 0

        with path.open("r", encoding="utf-8") as f:
            for row_idx, line in enumerate(f):
                if not line.strip():
                    continue
                raw = json.loads(line)
                page_chunks = self._record_to_chunks(
                    raw=raw,
                    source_filename=source_filename,
                    row_idx=row_idx,
                    start_chunk_idx=global_chunk_idx,
                    file_path=str(path),
                )
                documents.extend(page_chunks)
                global_chunk_idx += len(page_chunks)
        return documents

    def _record_to_chunks(
        self,
        raw: dict[str, Any],
        source_filename: str,
        row_idx: int,
        start_chunk_idx: int,
        file_path: str,
    ) -> list[dict]:
        doc_id = str(raw.get("doc_id") or f"row-{row_idx}").strip()
        source_type = str(raw.get("source_type") or "unknown").strip() or "unknown"
        title = str(raw.get("title") or "").strip()
        content = str(raw.get("content") or "").strip()
        text = f"# {title}\n\n{content}" if title else content
        if not text.strip():
            return []

        base_doc = {
            "filename": source_filename,
            "file_path": file_path,
            "file_type": "EnterpriseRAGBench",
            "page_number": row_idx,
            "doc_id": doc_id,
            "source_type": source_type,
            "title": title,
        }

        chunks: list[dict] = []
        chunk_idx = start_chunk_idx
        level_counters = {1: 0, 2: 0, 3: 0}
        level_1_size, level_1_overlap = self.levels[1]
        level_2_size, level_2_overlap = self.levels[2]
        level_3_size, level_3_overlap = self.levels[3]

        for level_1_text in self._sliding_chunks(text, level_1_size, level_1_overlap):
            level_1_id = self._build_chunk_id(doc_id, 1, level_counters[1])
            level_counters[1] += 1
            chunks.append(
                {
                    **base_doc,
                    "text": level_1_text,
                    "chunk_id": level_1_id,
                    "parent_chunk_id": "",
                    "root_chunk_id": level_1_id,
                    "chunk_level": 1,
                    "chunk_idx": chunk_idx,
                }
            )
            chunk_idx += 1

            for level_2_text in self._sliding_chunks(level_1_text, level_2_size, level_2_overlap):
                level_2_id = self._build_chunk_id(doc_id, 2, level_counters[2])
                level_counters[2] += 1
                chunks.append(
                    {
                        **base_doc,
                        "text": level_2_text,
                        "chunk_id": level_2_id,
                        "parent_chunk_id": level_1_id,
                        "root_chunk_id": level_1_id,
                        "chunk_level": 2,
                        "chunk_idx": chunk_idx,
                    }
                )
                chunk_idx += 1

                for level_3_text in self._sliding_chunks(level_2_text, level_3_size, level_3_overlap):
                    level_3_id = self._build_chunk_id(doc_id, 3, level_counters[3])
                    level_counters[3] += 1
                    chunks.append(
                        {
                            **base_doc,
                            "text": level_3_text,
                            "chunk_id": level_3_id,
                            "parent_chunk_id": level_2_id,
                            "root_chunk_id": level_1_id,
                            "chunk_level": 3,
                            "chunk_idx": chunk_idx,
                        }
                    )
                    chunk_idx += 1

        return chunks
