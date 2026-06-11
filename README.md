# Deedly CloudOps Demo

Deedly CloudOps Demo is an enterprise customer operations agent that combines RAG, customer memory, knowledge graph retrieval, tool calling, and evaluation traces in one workspace. The demo simulates a SaaS support and operations scenario: a user can ask about customer context, historical tickets, runbooks, ownership, incident impact, and response recommendations; the agent decides which tools to call and returns an answer with evidence panels for retrieved documents, graph paths, memory hits, and eval signals.

The project is designed as a resume-ready full-stack Agent demo. It uses FastAPI for the backend, LangChain/LangGraph-style workflows for tool orchestration, PostgreSQL for parent chunks and structured records, Milvus for vector retrieval, Neo4j-compatible graph construction, Redis for cache/session support, and a lightweight frontend workspace for interactive inspection.

## Features

- Unified chatbot workspace for customer operations questions.
- Enterprise knowledge base retrieval with chunking, vector search, rerank-ready interfaces, citations, and source display.
- Customer memory over profiles, historical tickets, preferences, and follow-up context.
- Enterprise knowledge graph entities and relations for customers, products, tickets, owners, teams, services, and documents.
- Multi-tool workflows for customer reply generation, knowledge graph question answering, and ticket priority analysis.
- Observable agent traces including tool calls, RAG sources, KG paths, memory hits, and evaluation metrics.
- Migration-oriented data model so a real company can map internal documents, customers, tickets, products, and relations into standard JSONL inputs.

## Project Layout

```text
backend/                 FastAPI app, agents, tools, RAG, memory, KG, DB clients
frontend/                Static chatbot workspace and evidence panels
data_pipelines/          Dataset preparation, enterprise KG extraction, migration validation
eval_harness/            Evaluation datasets, metrics, runners, and reports
mcp_servers/             MCP-like wrappers for KB, KG, memory, customer ops, and eval tools
configs/                 Runtime and tool capability configuration
docs/                    Architecture notes, data model, migration guide, and demo guide
scripts/                 Local indexing and demo scripts
tests/                   Unit, integration, and end-to-end test folders
```

## Configuration

Copy `.env_example` to `.env` and fill in your own model provider and local service settings:

```bash
cp .env_example .env
```

At minimum, configure:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
CHAT_MODEL
```

`GRADE_MODEL` can reuse `CHAT_MODEL`. Rerank settings are optional; when no rerank key or local rerank service is configured, rerank is disabled automatically. Embedding defaults to a local BGE-M3-compatible model path.

## Quick Start

The Python package imports use the package name `project`, so clone or place this repository in a folder named `project`, then run Python commands from its parent directory:

```bash
git clone https://github.com/wanzheng289/Deedly-CloudOps-Demo.git project
python3 -m venv .venv
source .venv/bin/activate
pip install -r project/requirements.txt
```

Start local infrastructure:

```bash
cd project
docker compose up -d postgres redis etcd minio milvus neo4j
cd ..
```

Prepare sample data and indexes:

```bash
python -m project.data_pipelines.enterprise_rag_bench.sample_documents --limit 400 --per-source-limit 50
python -m project.data_pipelines.enterprise_rag_bench.build_enterprise_qa
python -m project.data_pipelines.customer_support.prepare_support_cases
python -m project.data_pipelines.enterprise_kg.build_enterprise_entities
python -m project.data_pipelines.enterprise_kg.build_enterprise_relations
python -m project.data_pipelines.enterprise_kg.export_neo4j_import_files
python -m project.eval_harness.datasets.build_phase10_datasets --limit 100
python -m project.scripts.index_enterprise_sample --write --batch-size 32
```

Run the backend and frontend:

```bash
python -m project.backend.app
```

Open:

```text
http://localhost:8000
```

If port `8000` is already in use, change the app port in `.env`.

## Data Inputs

The demo can be built from public datasets, but the runtime design does not depend on any specific dataset. For real company migration, convert internal data into five standard JSONL groups:

- `documents`: runbooks, product docs, incident reviews, policies, support playbooks.
- `customers`: customer profiles, industry, products used, communication preferences.
- `tickets`: historical support cases, severity, status, product, issue type, resolution.
- `products_services`: products, services, environments, owners, runtime dependencies.
- `relations`: graph edges connecting customers, tickets, products, teams, documents, and services.

Schema examples and migration details are in:

```text
docs/architecture/enterprise_data_model.md
docs/architecture/standard_schema_examples.jsonl
docs/architecture/migration_pipeline.md
```

Validate migrated data:

```bash
python -m project.data_pipelines.migration.validate_standard_schema \
  --input-dir project/data/migration/standard
```

## Evaluation

Run offline evaluation datasets:

```bash
python -m project.eval_harness.runners.run_eval --dataset enterprise_qa --limit 10
python -m project.eval_harness.runners.run_eval --dataset customer_support_cases --limit 10
python -m project.eval_harness.runners.run_eval --dataset enterprise_kg_cases --limit 10
python -m project.eval_harness.runners.run_eval --dataset multidoc_dialogue_cases --limit 10
```

The harness reports retrieval, citation coverage, tool call accuracy, KG query accuracy, memory usefulness, answer faithfulness, and latency.

## Demo Questions

```text
客户 CustQRWQE 说生产环境无法登录 SSO，而且很着急，请判断优先级并给出下一步处理建议。
SSO 和客户 CustQRWQE 有什么关系？历史上出现过什么问题？
总结 perf-canary 部署到 prod 的注意事项，并说明涉及哪些团队或服务。
查看 CustWHHQY 的客户画像、历史工单和常见问题。
```

## Notes

This repository intentionally excludes local secrets, raw datasets, local model weights, virtual environments, generated runtime data, and personal job materials. Use `.env_example` as the configuration template and keep `.env` private.
