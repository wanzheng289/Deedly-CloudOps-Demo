# Migration Pipeline

This document describes how a real company can migrate its own operational data into the Enterprise Customer Ops Agent workspace.

The pipeline assumes that the target company can export data from systems such as Confluence, Jira, Zendesk, Slack, GitHub, Google Drive, CRM, service catalog, or internal databases.

## Goal

Convert heterogeneous enterprise data into the standard data model, then reuse the existing agent stack:

- RAG: PostgreSQL parent chunks + Milvus vectors
- Enterprise KG: Neo4j nodes and relations
- Memory: customer profile, historical tickets, durable facts
- Tool Calling: customer tools, KG tools, KB search tools
- Eval Harness: private regression cases

## Step 1: Data Connector

Purpose:

Export data from source systems without coupling the agent to vendor-specific APIs.

Typical sources:

| Source | Output |
|---|---|
| Confluence / Google Drive | documents |
| Jira / Zendesk / Intercom | tickets, relations |
| Slack / Gmail / Fireflies | documents, tickets, customer notes |
| GitHub | documents, products/services, relations |
| CRM / HubSpot / Salesforce | customers |
| CMDB / service catalog | products/services, ownership, dependencies |

Expected staging directory:

```text
data/migration/raw/
  confluence/
  jira/
  zendesk/
  slack/
  github/
  crm/
  service_catalog/
```

Security notes:

- Remove API tokens, secrets, passwords, credentials, and private keys.
- Mask customer PII when the demo does not require exact names.
- Preserve stable IDs so relations can still be built.
- Preserve source URLs only when the runtime user has permission to view them.

## Step 2: Normalize

Purpose:

Map source-specific exports into the standard JSONL schema.

Expected output:

```text
data/migration/standard/
  documents.jsonl
  customers.jsonl
  tickets.jsonl
  products_services.jsonl
  relations.jsonl
```

Schema reference:

- `docs/architecture/enterprise_data_model.md`
- `docs/architecture/standard_schema_examples.jsonl`

Validation command:

```bash
# Run from the parent directory that contains the cloned `project/` folder.
python -m project.data_pipelines.migration.validate_standard_schema \
  --input-dir project/data/migration/standard
```

The validator checks required fields, duplicate IDs, JSONL formatting, and basic field types. It writes:

```text
data/migration/validation_summary.json
```

## Step 3: Index

Purpose:

Turn normalized `documents.jsonl` into retrievable knowledge.

Current demo equivalent:

```bash
python -m project.scripts.index_enterprise_sample --write --batch-size 32
```

Target migration behavior:

```text
documents.jsonl
  -> chunking
  -> parent_chunks in PostgreSQL
  -> dense vectors in Milvus
  -> document metadata for citations
```

Implementation notes:

- Keep original `doc_id` in every chunk.
- Store `source_type`, `title`, `source_uri`, `owner_team`, `product`, `service`, and ACL metadata.
- RAG citations should reference `doc_id`, `title`, and source type.
- ACL filtering should happen before final answer generation in production.

## Step 4: Build KG

Purpose:

Create Enterprise KG nodes and relations from `customers`, `tickets`, `products_services`, `documents`, and `relations`.

Current demo commands:

```bash
python -m project.data_pipelines.enterprise_kg.build_enterprise_entities
python -m project.data_pipelines.enterprise_kg.build_enterprise_relations
python -m project.data_pipelines.enterprise_kg.export_neo4j_import_files
```

Target migration behavior:

```text
customers.jsonl          -> Customer nodes
tickets.jsonl            -> SupportTicket nodes
documents.jsonl          -> Document nodes
products_services.jsonl  -> Product / Service / Team / Env nodes
relations.jsonl          -> Neo4j relationships
```

Recommended graph constraints:

- `Customer.customer_id` unique
- `SupportTicket.ticket_id` unique
- `Document.doc_id` unique
- `Product.name` unique
- `Service.name` unique
- relation edges preserve `confidence` and `evidence_doc_id`

## Step 5: Seed Memory

Purpose:

Generate customer memory and support context from structured customer and ticket history.

Inputs:

- `customers.jsonl`
- `tickets.jsonl`

Memory outputs:

| Memory Type | Example |
|---|---|
| Profile Memory | customer segment, products, SLA, contact preference |
| Historical Ticket Memory | recurring issue types, resolved incidents |
| Risk Memory | escalation tendency, outage sensitivity, high priority count |
| Preference Memory | preferred communication channel and response format |

Current demo uses:

```text
data/processed/customer_support/customer_profiles.jsonl
data/processed/customer_support/support_tickets.jsonl
data/processed/customer_support/memory_items.jsonl
```

Target migration behavior:

```text
customers.jsonl + tickets.jsonl
  -> customer profile store
  -> durable memory items
  -> searchable memory index
```

## Step 6: Eval Harness

Purpose:

Create a company-specific regression suite before the agent is used in front of real users.

Eval case types:

| Case Type | Checks |
|---|---|
| Enterprise QA | retrieval recall, citation coverage, answer faithfulness |
| Customer Support | memory usefulness, ticket lookup, response quality |
| KG Query | graph path correctness, owner lookup, impact tracing |
| Tool Routing | expected tool calls and call order |

Current demo command:

```bash
python -m project.eval_harness.runners.run_eval --dataset enterprise_qa --limit 20 --run-retrieval
```

Target migration behavior:

```text
standard data
  -> private eval cases
  -> regression reports
  -> prompt/routing/retrieval iteration gate
```

## End-to-End Checklist

1. Export source data into `data/migration/raw/`.
2. Normalize into `data/migration/standard/*.jsonl`.
3. Run schema validation.
4. Index documents into PostgreSQL and Milvus.
5. Build Neo4j nodes and relations.
6. Seed customer memory.
7. Generate private eval cases.
8. Run regression eval.
9. Start the FastAPI app and test the workspace.

## Interview Explanation

The project does not depend on one fixed public dataset. The demo uses public data to construct a sample company, but the production migration path is schema-driven: map enterprise systems into `documents`, `customers`, `tickets`, `products_services`, and `relations`, then reuse the same RAG, KG, Memory, Tool Calling, and Eval layers.
