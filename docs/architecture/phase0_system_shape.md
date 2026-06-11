# Phase 0: Final System Shape

本阶段目标是明确最终系统形态，避免后续开发变成“RAG、KG、Memory、MCP 功能堆叠”。项目主线固定为：

```text
企业客服/运营 Agent
+ Vector-RAG
+ Enterprise KG
+ Customer Memory
+ Multi-Tool Workflow
+ Eval Harness
```

## 1. Product Positioning

本项目不是单纯的企业文档问答 Demo，而是面向企业客服/运营场景的可评测 Multi-Tool Agent 平台。

系统需要回答的问题类型包括：

- 企业文档知识问答：某功能、部署方式、API 限制、运行手册如何说明。
- 客户上下文查询：某客户之前反馈过什么、涉及哪个产品/模块、历史处理结果是什么。
- 工单/运营分析：当前问题优先级、类似历史工单、可能影响范围、下一步动作。
- 图谱关系查询：客户、产品、工单、文档、团队、服务、Issue 之间的结构化关系。
- 客服回复生成：结合客户历史、企业文档和图谱路径，生成可发给客户的回复草稿。

## 2. Core Chains

### 2.1 Enterprise Knowledge Base RAG

用户问企业文档问题时，Agent 调用 `search_enterprise_kb`。

数据来源：

- `../data/raw/enterprise_rag_bench/documents.jsonl`

主要组件：

- `backend/rag/`
- `backend/tools/enterprise_kb_tools.py`
- Milvus dense/sparse hybrid retrieval
- PostgreSQL parent chunk store
- Rerank/citation builder

预期输出：

- 基于文档内容的回答
- 引用来源
- RAG trace

### 2.2 Enterprise Knowledge Graph

系统从企业文档和客服对话中抽取企业实体和关系，写入 Neo4j。

数据来源：

- `../data/raw/enterprise_rag_bench/documents.jsonl`
- `../data/raw/customer_support/customer_support_data.csv`

实体类型：

- `Customer`
- `Product`
- `Module`
- `SupportTicket`
- `Document`
- `Issue`
- `Team`
- `Service`
- `DeploymentEnv`
- `SLA`
- `FAQ`
- `Version`

关系类型：

- `CUSTOMER_OPENED_TICKET`
- `TICKET_MENTIONS_PRODUCT`
- `TICKET_MENTIONS_MODULE`
- `DOCUMENT_EXPLAINS_PRODUCT`
- `DOCUMENT_EXPLAINS_MODULE`
- `ISSUE_RELATED_TO_VERSION`
- `TEAM_OWNS_SERVICE`
- `PRODUCT_DEPENDS_ON_SERVICE`
- `CUSTOMER_USES_PRODUCT`
- `FAQ_ANSWERS_ISSUE_TYPE`

RAGQnASystem 的迁移方式：

- 迁移实体/关系/schema 设计方法，而不是迁移医疗业务场景。
- 迁移 Neo4j 图谱构建和 KG 查询工具化思路。
- 企业 KG 负责结构化关系查询，Vector-RAG 负责长文档原文解释。

### 2.3 Customer/Ops Memory

系统从客服对话中生成客户画像、历史工单和长期记忆。

数据来源：

- `../data/raw/customer_support/customer_support_data.csv`

Memory 类型：

- Session Memory：当前对话上下文。
- Profile Memory：客户画像、产品、问题类型、渠道、历史工单。
- Domain Memory：常见失败案例、高价值 FAQ、典型解决方案、Agent 失败案例。

预期工具：

- `get_customer_profile`
- `search_customer_tickets`
- `update_customer_memory`
- `create_followup_task`

### 2.4 Multi-Tool Agent

Agent 不直接“一问一搜”，而是先判断任务类型，再选择工具。

核心工具：

- `search_enterprise_kb`
- `enterprise_kg_query`
- `get_customer_profile`
- `search_customer_tickets`
- `update_customer_memory`
- `draft_customer_reply`
- `classify_intent`
- `detect_sentiment`
- `assign_priority`

核心 workflow：

- 企业知识问答
- 客服回复生成
- 工单优先级判断
- 企业图谱增强问答

### 2.5 Eval Harness

系统必须可评测，而不是只靠人工体验。

数据来源：

- `../data/raw/enterprise_rag_bench/questions.jsonl`
- 自建客服/图谱 case
- 后续补充 Doc2Dial/MultiDoc2Dial 多轮评测

指标：

- Retrieval Recall@K
- Tool Call Accuracy
- KG Query Accuracy
- Citation Coverage
- Answer Faithfulness
- Memory Usefulness
- Latency

第一版只强制实现：

- Retrieval Recall@K
- Citation Coverage

## 3. Component Boundary

| Layer | Responsibility | Not Responsible For |
|---|---|---|
| `data_pipelines/` | 原始数据清洗、抽样、转换、生成 processed 数据 | 在线问答和工具调用 |
| `backend/rag/` | chunk、embedding、Milvus 写入、检索、rerank、citation | 客户画像和图谱关系推理 |
| `backend/knowledge_graph/` | 企业实体/关系 schema、Neo4j 导入、图谱查询 | 长文档语义检索 |
| `backend/memory/` | 会话、客户画像、长期记忆读写和召回 | 文档切分和图谱构建 |
| `backend/tools/` | Agent 可调用工具封装 | 复杂 workflow 编排 |
| `backend/workflows/` | 多步骤任务编排 | 底层 DB 客户端细节 |
| `eval_harness/` | 评测数据、指标、runner、报告 | 业务在线服务 |
| `mcp_servers/` | 稳定工具的协议化服务 | 初期核心功能试验 |

## 4. MVP Acceptance Criteria

Phase 0 完成后，后续开发必须围绕以下 MVP 判断：

1. 企业 RAG 能从 EnterpriseRAG-Bench 抽样文档中检索并回答，回答包含来源。
2. 客服数据能生成客户画像和历史工单。
3. 企业 KG 能生成 nodes/relations，并支持至少一种 Neo4j 图谱查询。
4. Agent 能根据问题选择至少两类工具：企业知识库检索、客户/工单查询。
5. Eval Harness 能跑 EnterpriseRAG-Bench 的小样本评测，并输出 Recall@K 与 Citation Coverage。

## 5. First Demo Script

第一版 Demo 只需要覆盖一个组合场景：

> 这个客户之前反馈过部署失败，现在又问私有化部署支持哪些 GPU，帮我查资料并生成一版客服回复。

预期链路：

1. 识别客户、产品、部署/GPU 等实体。
2. 查询客户画像。
3. 查询历史工单。
4. 查询企业图谱中的客户-工单-产品关系。
5. 检索企业文档中 GPU/私有化部署相关内容。
6. 生成客服回复，包含来源、图谱路径和待确认事项。

## 6. Explicit Non-Goals

当前阶段不做：

- 全量导入 51 万企业文档。
- 复杂 LLM 实体抽取训练。
- 完整 MCP 实现。
- 前端精装修。
- 医疗问答插件。
- 本地大模型推理服务优化。

这些能力可以作为后续扩展，但不能阻塞 MVP。

