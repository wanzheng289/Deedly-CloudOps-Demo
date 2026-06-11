# Deedly CloudOps Demo Workspace

`Deedly CloudOps` is the virtual company used by this project to make public datasets feel like one coherent enterprise customer-ops environment.

It is not a real company. It is a concept layer over EnterpriseRAG-Bench, Customer Support Conversations, Enterprise KG outputs, and demo eval cases.

## Company Profile

| Item | Value |
|---|---|
| Company | Deedly CloudOps |
| Workspace | Deedly CloudOps Demo |
| Domain | SaaS customer operations and cloud service support |
| Users | support agents, customer success, on-call engineers, ops leads |
| Agent scope | customer memory, ticket triage, enterprise RAG, Enterprise KG, eval harness |

## Products

The demo workspace focuses on a few recurring products and services:

| Product / Service | Role in Demo |
|---|---|
| `SSO` | Access, identity, login, RBAC, SAML troubleshooting |
| `perf-canary` | Deployment, rollout, rollback, prod readiness, owner lookup |
| `Course Access` | Customer-facing access issue connected to SSO support history |
| `API` | Generic service/API support examples from the public ticket data |
| `Billing` | Customer support issue category |

## Customers

Example customers are anonymized IDs generated from the support dataset:

| Customer | Demo Role |
|---|---|
| `CustQRWQE` | Primary customer used in urgent SSO and customer-memory demos |
| `CustBBTPM` | Additional SSO/product relation example |
| `CustBDBKJ` | Additional SSO/product relation example |
| `CustBGFJM` | Additional SSO/product relation example |

## Teams

The Enterprise KG and playbooks use team-like entities to make ownership and routing questions more realistic:

| Team | Responsibility |
|---|---|
| `eng-runtime` | runtime, deployment, canary rollout |
| `eng-infra` | platform infrastructure and production reliability |
| `eng-identity` | SSO, identity, auth, RBAC |
| `support-oncall` | customer incident triage |
| `customer-success` | customer communication and follow-up |

## Data Sources

Public data is wrapped as Deedly CloudOps source systems:

| Source | Use |
|---|---|
| `jira` | issue/ticket-like records and engineering context |
| `confluence` | runbooks and internal docs |
| `fireflies` | meeting notes and operational context |
| `hubspot` | customer and account-like context |
| `gmail` | email threads and customer communication |
| `github` | engineering docs, issues, repos, PR-like context |

## Demo Story

The user should understand the workspace as:

> Deedly CloudOps is a SaaS operations company. Customers use products such as SSO and Course Access. Support tickets, internal docs, runbooks, meetings, and engineering records are indexed into one agent workspace. The agent can combine customer memory, historical tickets, Enterprise KG, document RAG, and eval traces to answer support and operations questions.

This lets the project avoid feeling like a pile of unrelated datasets. The public data becomes one coherent simulated business.

## Migration Story

In a real company, Deedly CloudOps would be replaced by that company's own workspace:

1. Replace demo documents with company knowledge-base exports.
2. Replace demo customers with CRM/account records.
3. Replace demo tickets with Zendesk/Jira/Intercom support records.
4. Replace demo products/services with service catalog or CMDB data.
5. Replace demo KG relations with extracted or imported enterprise relations.
6. Re-run RAG indexing, KG build, memory seed, and eval harness.

The rest of the agent stack stays the same.
