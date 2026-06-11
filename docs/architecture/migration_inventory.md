# Migration Inventory

This file records the first migration from `SuperMew` and `RAGQnASystem` into the new `project/` layout.

## Migrated From SuperMew

| Source | Target | Purpose |
|---|---|---|
| `SuperMew/backend/database.py` | `project/backend/db/postgres.py` | SQLAlchemy engine, session factory, DB initialization |
| `SuperMew/backend/cache.py` | `project/backend/db/redis_cache.py` | Redis JSON cache wrapper |
| `SuperMew/backend/models.py` | `project/backend/db/models.py` | User, chat session, chat message, parent chunk ORM models |
| `SuperMew/backend/auth.py` | `project/backend/api/auth.py` | JWT auth, password hashing, role checks |
| `SuperMew/backend/document_loader.py` | `project/backend/rag/document_loader.py` | PDF/Word/Excel loading and three-level chunking |
| `SuperMew/backend/embedding.py` | `project/backend/rag/embedding.py` | Dense embeddings and persistent BM25 sparse vectors |
| `SuperMew/backend/milvus_client.py` | `project/backend/db/milvus.py` | Milvus collection management and hybrid retrieval |
| `SuperMew/backend/milvus_writer.py` | `project/backend/rag/indexer.py` | Dense/sparse embedding generation and Milvus writes |
| `SuperMew/backend/parent_chunk_store.py` | `project/backend/rag/parent_store.py` | PostgreSQL + Redis parent chunk store for auto-merging |
| `SuperMew/backend/rag_utils.py` | `project/backend/rag/retriever.py` | Hybrid retrieval, rerank, query expansion, auto-merging |
| `SuperMew/backend/rag_pipeline.py` | `project/backend/workflows/enterprise_rag_workflow.py` | LangGraph RAG workflow |
| `SuperMew/backend/tools.py` | `project/backend/tools/enterprise_kb_tools.py` | Knowledge-base tool, weather sample tool, RAG trace queue |
| `SuperMew/backend/agent.py` | `project/backend/agents/main_agent.py` | Main agent, session storage, streaming response flow |
| `SuperMew/backend/schemas.py` | `project/backend/schemas/chat.py` | Pydantic schemas for auth, chat, sessions, documents |
| `SuperMew/backend/api.py` | `project/backend/api/routes_legacy.py` | Legacy combined routes, to be split later |
| `SuperMew/backend/upload_jobs.py` | `project/backend/api/upload_jobs.py` | Upload/delete progress tracking |

## Added For New Project

| Target | Purpose |
|---|---|
| `project/backend/app.py` | New FastAPI entrypoint for the project layout |
| `project/data_pipelines/enterprise_kg/prepare_ragqna_kg_reference.py` | Non-interactive RAGQnASystem KG reference extraction pipeline |
| `data/processed/ragqna_kg_reference/` | Optional normalized KG reference output generated from `RAGQnASystem/data/medical_new_2.json` |

## Important Refactors Already Applied

- Replaced flat imports such as `from database import ...` with `project.backend...` imports.
- Moved default BM25 state path to `project/data/runtime/bm25_state.json`.
- Kept `routes_legacy.py` as a temporary compatibility layer. Split it into `chat.py`, `documents.py`, `sessions.py`, and `eval.py` once the new APIs stabilize.

## Next Refactor Targets

1. Rename `search_knowledge_base` to `search_enterprise_kb` and keep a backward-compatible alias.
2. Replace the inherited agent system prompt with an enterprise customer-ops prompt.
3. Split `routes_legacy.py` into focused route modules.
4. Add `CustomerProfile`, `SupportTicket`, and `MemoryItem` ORM models.
5. Add data pipelines for EnterpriseRAG-Bench and Customer Support Conversations.
6. Introduce eval datasets generated from `EnterpriseRAG-Bench/questions.jsonl`.
