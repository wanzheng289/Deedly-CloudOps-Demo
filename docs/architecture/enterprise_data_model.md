# Enterprise Data Model

This document defines the normalized data contract for migrating a real company into the Enterprise Customer Ops Agent workspace.

The demo currently uses public datasets to build `Deedly CloudOps Demo`, but the agent is designed around these stable abstractions rather than any single dataset:

- `documents`
- `customers`
- `tickets`
- `products_services`
- `relations`

If a company can map its internal systems into these JSONL files, the existing RAG, Enterprise KG, Memory, Tool Calling, and Eval Harness layers can be reused.

## Data Flow

```text
Confluence / Jira / Zendesk / Slack / GitHub / CRM
  -> normalize to standard JSONL
  -> documents -> PostgreSQL parent chunks + Milvus vectors
  -> customers/tickets -> memory stores + customer tools
  -> products_services/relations -> Neo4j Enterprise KG
  -> eval cases -> regression harness
```

## documents.jsonl

Enterprise documents, runbooks, FAQs, meeting notes, support knowledge, and engineering docs.

Required fields:

| Field | Type | Notes |
|---|---|---|
| `doc_id` | string | Globally unique document ID |
| `title` | string | Human-readable title |
| `content` | string | Full text before chunking |
| `source_type` | string | Source system, e.g. `confluence`, `jira`, `github` |

Optional fields:

| Field | Type | Notes |
|---|---|---|
| `source_uri` | string | Original URL |
| `created_at` | string | ISO timestamp |
| `updated_at` | string | ISO timestamp |
| `owner_team` | string | Responsible team |
| `product` | string | Product name |
| `service` | string | Service name |
| `tags` | list[string] | Search and routing tags |
| `acl` | list[string] | Access-control groups |

Downstream usage:

- RAG retrieval and citation
- Document-grounded QA eval
- KG relation evidence

## customers.jsonl

Customer profile and durable customer memory seed data.

Required fields:

| Field | Type | Notes |
|---|---|---|
| `customer_id` | string | Globally unique customer ID |
| `name` | string | Customer display name, can be anonymized |

Recommended fields:

| Field | Type | Notes |
|---|---|---|
| `industry` | string | Customer industry |
| `segment` | string | Customer segment |
| `products` | list[string] | Products used by customer |
| `sla_tier` | string | SLA tier |
| `priority_tier` | string | Support priority |
| `contact_preference` | string | Preferred contact channel |
| `risk_tags` | list[string] | Churn, escalation, outage sensitivity |
| `last_seen_at` | string | ISO timestamp |
| `summary` | string | Profile summary |

Downstream usage:

- Customer profile memory
- Customer-product graph relations
- Support workflow personalization

## tickets.jsonl

Historical support tickets and customer conversation records.

Required fields:

| Field | Type | Notes |
|---|---|---|
| `ticket_id` | string | Ticket ID |
| `customer_id` | string | Linked customer |
| `summary` | string | Short issue summary |

Recommended fields:

| Field | Type | Notes |
|---|---|---|
| `product` | string | Related product |
| `service` | string | Related service |
| `issue_type` | string | Issue category |
| `status` | string | `open`, `resolved`, `escalated`, etc. |
| `priority` | string | `low`, `medium`, `high`, `urgent` |
| `sentiment` | string | Customer sentiment |
| `created_at` | string | ISO timestamp |
| `updated_at` | string | ISO timestamp |
| `messages` | list[object] | Optional conversation turns |
| `resolution` | string | Final resolution |
| `linked_doc_ids` | list[string] | Supporting documents |

Downstream usage:

- Ticket search tools
- Customer memory
- Priority classification
- Ticket-product and ticket-issue KG relations

## products_services.jsonl

Product, service, module, environment, and ownership metadata.

Required fields:

| Field | Type | Notes |
|---|---|---|
| `entity_id` | string | Unique entity ID |
| `name` | string | Name, e.g. `SSO`, `perf-canary` |
| `entity_type` | string | `product`, `service`, `module`, `environment` |

Recommended fields:

| Field | Type | Notes |
|---|---|---|
| `description` | string | Description |
| `owner_team` | string | Owning team |
| `runtime_envs` | list[string] | `staging`, `prod`, etc. |
| `dependencies` | list[string] | Dependent services |
| `runbook_doc_ids` | list[string] | Related runbooks |
| `repo` | string | Source code repository |

Downstream usage:

- Owner lookup
- Dependency graph
- Impact analysis

## relations.jsonl

Standard KG edge input.

Required fields:

| Field | Type | Notes |
|---|---|---|
| `source_id` | string | Source entity ID |
| `source_type` | string | Source entity type |
| `target_id` | string | Target entity ID |
| `target_type` | string | Target entity type |
| `relation_type` | string | Edge label |

Recommended fields:

| Field | Type | Notes |
|---|---|---|
| `confidence` | float | Relation confidence |
| `evidence_doc_id` | string | Supporting document |
| `evidence_text` | string | Supporting excerpt |
| `created_at` | string | ISO timestamp |

Recommended relation types:

| Relation | Meaning |
|---|---|
| `CUSTOMER_USES_PRODUCT` | Customer uses product |
| `CUSTOMER_OPENED_TICKET` | Customer opened ticket |
| `TICKET_MENTIONS_PRODUCT` | Ticket mentions product |
| `TICKET_HAS_ISSUE` | Ticket has issue category |
| `DOCUMENT_EXPLAINS_PRODUCT` | Document explains product |
| `DOCUMENT_MENTIONS_SERVICE` | Document mentions service |
| `DOCUMENT_MENTIONS_TEAM` | Document mentions team |
| `TEAM_OWNS_SERVICE` | Team owns service |
| `SERVICE_DEPENDS_ON_SERVICE` | Service dependency |
| `SERVICE_RUNS_IN_ENV` | Service runs in environment |
| `ISSUE_AFFECTS_PRODUCT` | Issue affects product |

## Current Demo Mapping

| Standard File | Demo Source | Current Output |
|---|---|---|
| `documents.jsonl` | EnterpriseRAG-Bench documents | `data/processed/enterprise_rag_bench/sample_documents.jsonl` |
| `customers.jsonl` | Customer Support Conversations derived profiles | `data/processed/customer_support/customer_profiles.jsonl` |
| `tickets.jsonl` | Customer Support Conversations derived tickets | `data/processed/customer_support/support_tickets.jsonl` |
| `products_services.jsonl` | Ticket fields + document/entity extraction | `data/processed/enterprise_kg/nodes.jsonl` |
| `relations.jsonl` | Ticket fields + entity relation extraction | `data/processed/enterprise_kg/relations.jsonl` |

## Migration Checklist

1. Export raw data from source systems.
2. Remove secrets, PII, credentials, and customer-confidential content.
3. Normalize records into the standard JSONL files.
4. Index `documents` into PostgreSQL and Milvus.
5. Load `relations` and `products_services` into Neo4j.
6. Seed customer memory from `customers` and `tickets`.
7. Generate eval cases from real workflow questions.
8. Run regression eval before exposing the workspace to users.
