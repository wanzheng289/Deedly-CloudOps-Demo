const {useEffect, useMemo, useRef, useState} = React;
const h = React.createElement;

const defaultQuery = "客户 CustQRWQE 说生产环境无法登录 SSO，而且很着急，请判断优先级并给出下一步处理建议。";

const examples = [
  ["SSO 紧急工单", "客户 CustQRWQE 说生产环境无法登录 SSO，而且很着急，请判断优先级并给出下一步处理建议。"],
  ["生成客服回复", "客户 CustQRWQE 之前有 SSO 工单，现在问部署 perf-canary 是否会影响访问，请结合历史和文档生成回复。"],
  ["负责人和部署文档", "perf-canary 谁负责，部署到 prod 时文档怎么说？"],
  ["客户图谱关系", "SSO 和客户 CustQRWQE 有什么关系？历史上出现过什么问题？"],
];

function emptyRun(overrides = {}) {
  return {
    tools: [],
    sources: [],
    paths: [],
    memory: [],
    eval: {},
    ...overrides,
  };
}

function runFromPayload(payload, query) {
  return {
    tools: payload?.tools || [],
    sources: payload?.sources || [],
    paths: payload?.paths || [],
    memory: payload?.memory || [],
    eval: payload?.eval || {},
    rag_trace: payload?.rag_trace,
    tool_outputs: payload?.tool_outputs || [],
    raw: payload?.raw,
    query: payload?.query || query,
    scenario: payload?.scenario,
  };
}

function buildNoAnswerDiagnostic(payload) {
  const tools = payload?.tools?.length ? payload.tools.join(", ") : "none";
  const sourceCount = payload?.sources?.length || 0;
  const pathCount = payload?.paths?.length || 0;
  const memoryCount = payload?.memory?.length || 0;
  const rawResponse = payload?.raw?.response;

  return [
    "**运行诊断**",
    "后端请求已经完成，但没有返回最终 answer。",
    "",
    `- 工具调用：${tools}`,
    `- RAG Sources：${sourceCount}`,
    `- KG Paths：${pathCount}`,
    `- Memory Hits：${memoryCount}`,
    `- raw.response：${rawResponse ? "present" : "empty"}`,
    "",
    "优先检查右侧 Evidence Brief：如果工具有输出但 answer 为空，通常是生成阶段没有写入最终消息；如果 RAG/KG/Memory 都为空，通常是检索或路由没有命中。",
  ].join("\n");
}

function CanvasBackdrop() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    let frame = 0;
    let raf = 0;

    function resize() {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(canvas.clientWidth * ratio);
      canvas.height = Math.floor(canvas.clientHeight * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    function draw() {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      ctx.clearRect(0, 0, width, height);
      ctx.strokeStyle = "rgba(0, 0, 0, 0.055)";
      ctx.lineWidth = 1;

      for (let x = 0; x < width; x += 28) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += 28) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      const pulse = (Math.sin(frame / 45) + 1) / 2;
      ctx.fillStyle = `rgba(0, 143, 71, ${0.08 + pulse * 0.08})`;
      ctx.fillRect(width - 210, 36, 150, 10);
      ctx.fillStyle = `rgba(255, 153, 10, ${0.06 + pulse * 0.06})`;
      ctx.fillRect(42, height - 70, 220, 12);

      frame += 1;
      raf = requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return h("canvas", {className: "canvas-backdrop", ref: canvasRef, "aria-hidden": "true"});
}

function App() {
  const [input, setInput] = useState(defaultQuery);
  const [isRunning, setIsRunning] = useState(false);
  const [workspace, setWorkspace] = useState(null);
  const [workspaceError, setWorkspaceError] = useState("");
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      sender: "agent",
      text: "我是统一企业客服/运营 Agent。你可以直接输入问题，我会自动决定是否调用客户记忆、历史工单、企业知识库、企业图谱和评测链路。",
      run: emptyRun({tools: ["ready_for_question"]}),
    },
  ]);
  const [currentRun, setCurrentRun] = useState(emptyRun({tools: ["ready_for_question"]}));
  const [selectedMessageId, setSelectedMessageId] = useState("welcome");
  const chatRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    fetch("/workspace/explorer")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Workspace explorer failed: ${response.status}`);
        }
        return response.json();
      })
      .then((payload) => {
        if (isMounted) {
          setWorkspace(payload);
        }
      })
      .catch((error) => {
        if (isMounted) {
          setWorkspaceError(error.message);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, isRunning]);

  const runLabel = useMemo(() => {
    if (isRunning) return "RUNNING";
    if (currentRun.tools?.length) return "TRACE READY";
    return "IDLE";
  }, [isRunning, currentRun]);

  function selectWorkspaceItem(item) {
    if (item?.query) {
      setInput(item.query);
    }
  }

  async function runAgent(customQuery) {
    if (isRunning) return;
    const query = (customQuery || input || defaultQuery).trim();
    if (!query) return;

    const userMessage = {id: `user-${Date.now()}`, sender: "user", text: query};
    const pendingId = `agent-${Date.now()}`;
    const pendingRun = emptyRun({tools: ["request_unified_agent"], query});
    setMessages((prev) => [...prev, userMessage, {
      id: pendingId,
      sender: "agent",
      text: "正在调用统一 Agent，请稍等...",
      pending: true,
      run: pendingRun,
      query,
    }]);
    setCurrentRun(pendingRun);
    setSelectedMessageId(pendingId);
    setIsRunning(true);

    try {
      const response = await fetch("/agent/run", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          scenario: "unifiedChat",
          query,
          session_id: "frontend_deedly_workspace",
          user_id: "frontend_demo_user",
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Request failed: ${response.status}`);
      }
      const run = runFromPayload(payload, query);
      setMessages((prev) => prev.map((item) => (
        item.id === pendingId ? {
          id: pendingId,
          sender: "agent",
          text: payload.answer || buildNoAnswerDiagnostic(payload),
          diagnostic: !payload.answer,
          run,
          query,
        } : item
      )));
      setCurrentRun(run);
      setSelectedMessageId(pendingId);
      setInput("");
    } catch (error) {
      const errorRun = emptyRun({tools: ["request_unified_agent_failed"], query, error: error.message});
      setMessages((prev) => prev.map((item) => (
        item.id === pendingId ? {
          id: pendingId,
          sender: "agent",
          text: `运行失败：${error.message}`,
          error: true,
          run: errorRun,
          query,
        } : item
      )));
      setCurrentRun(errorRun);
      setSelectedMessageId(pendingId);
    } finally {
      setIsRunning(false);
    }
  }

  return h("div", {className: "app-shell"},
    h(CanvasBackdrop),
    h(Header, {runLabel, workspace}),
    h("div", {className: "workspace-frame"},
      h(Sidebar),
      h("main", {className: "chat-column"},
        h("div", {className: "status-strip"},
          h("div", {className: "status-left"},
            h("span", {className: "live-dot"}),
            h("span", null, `WORKSPACE: ${workspace?.workspace?.name || "ENTERPRISE CUSTOMER OPS AGENT"}`)
          ),
          h("span", {className: "status-right"}, "SECURE TOOL ROUTER")
        ),
        h("div", {className: "example-row"},
          examples.map(([label, query]) => h("button", {
            key: label,
            className: "example-chip neo-btn",
            disabled: isRunning,
            onClick: () => setInput(query),
            type: "button",
          }, `[ ${label} ]`))
        ),
        h(WorkspaceExplorer, {
          workspace,
          workspaceError,
          onSelectItem: selectWorkspaceItem,
        }),
        h(ScenarioPlaybook, {
          scenarios: workspace?.scenarios || [],
          isRunning,
          onLoadScenario: (scenario) => setInput(scenario.query || ""),
          onRunScenario: (scenario) => runAgent(scenario.query || ""),
        }),
        h("div", {className: "chat-window", ref: chatRef},
          messages.map((message) => h(ChatMessage, {
            key: message.id,
            message,
            currentRun,
            selected: selectedMessageId === message.id,
            onSelectRun: (run, id) => {
              if (run) {
                setCurrentRun(run);
                setSelectedMessageId(id);
              }
            },
          }))
        ),
        h("form", {
          className: "composer",
          onSubmit: (event) => {
            event.preventDefault();
            runAgent();
          },
        },
          h("button", {className: "attach-btn", type: "button", title: "Attach context"}, "+"),
          h("input", {
            value: input,
            onChange: (event) => setInput(event.target.value),
            placeholder: "Message deedly... Ask about customers, tickets, runbooks, owners, impact.",
          }),
          h("button", {className: "run-btn neo-btn", disabled: isRunning, type: "submit"}, isRunning ? "RUNNING" : "RUN")
        )
      ),
      h(RightWorkspace, {currentRun})
    )
  );
}

function ScenarioPlaybook({scenarios, isRunning, onLoadScenario, onRunScenario}) {
  return h("section", {className: "scenario-playbook neo-box"},
    h("div", {className: "playbook-header"},
      h("div", null,
        h("div", {className: "explorer-kicker"}, "DEMO SCENARIO PLAYBOOK"),
        h("h2", null, "Choose a workflow to demonstrate")
      ),
      h("p", null, "每个场景的输入、工具链和期望看到的证据")
    ),
    scenarios.length
      ? h("div", {className: "scenario-grid"},
          scenarios.map((scenario, idx) => h("article", {className: "scenario-card", key: scenario.id || idx},
            h("div", {className: "scenario-topline"},
              h("span", {className: "scenario-index"}, `0${idx + 1}`),
              h("span", {className: "scenario-subtitle"}, scenario.subtitle)
            ),
            h("h3", null, scenario.title),
            h("p", {className: "scenario-query"}, scenario.query),
            h("div", {className: "scenario-uses"},
              (scenario.uses || []).map((item) => h("span", {key: item}, item))
            ),
            h("div", {className: "scenario-detail"},
              h("strong", null, "Expected evidence"),
              h("ul", null, (scenario.expected || []).slice(0, 3).map((item) => h("li", {key: item}, item)))
            ),
            h("div", {className: "scenario-tools"},
              h("strong", null, "Tools"),
              h("code", null, (scenario.tools || []).join(" → "))
            ),
            h("div", {className: "scenario-actions"},
              h("button", {
                className: "scenario-btn",
                disabled: isRunning,
                onClick: () => onLoadScenario(scenario),
                type: "button",
              }, "LOAD"),
              h("button", {
                className: "scenario-btn scenario-run neo-btn",
                disabled: isRunning,
                onClick: () => onRunScenario(scenario),
                type: "button",
              }, isRunning ? "RUNNING" : "RUN")
            )
          ))
        )
      : h("div", {className: "explorer-empty"}, "Loading scenario playbook...")
  );
}

function WorkspaceExplorer({workspace, workspaceError, onSelectItem}) {
  const sections = [
    ["Customers", workspace?.customers || []],
    ["Products", workspace?.products || []],
    ["Documents", workspace?.documents || []],
    ["Tickets", workspace?.tickets || []],
  ];
  const overview = workspace?.overview || {};

  return h("section", {className: "workspace-explorer neo-box"},
    h("div", {className: "explorer-header"},
      h("div", null,
        h("div", {className: "explorer-kicker"}, "WORKSPACE EXPLORER"),
        h("h2", null, workspace?.workspace?.name || "Loading workspace...")
      ),
      h("div", {className: "explorer-stats"},
        h("span", null, `${overview.customers || 0} customers`),
        h("span", null, `${overview.tickets || 0} tickets`),
        h("span", null, `${overview.documents || 0} docs`),
        h("span", null, `${overview.kg_nodes || 0} kg nodes`)
      )
    ),
    workspaceError
      ? h("div", {className: "explorer-error"}, workspaceError)
      : h(React.Fragment, null,
          h(DemoCompanyCard, {company: workspace?.demo_company}),
          h("div", {className: "explorer-grid"},
            sections.map(([title, items]) => h(ExplorerSection, {
              key: title,
              title,
              items,
              onSelectItem,
            }))
          )
        )
  );
}

function DemoCompanyCard({company}) {
  if (!company) {
    return h("div", {className: "demo-company-card"},
      h("div", {className: "demo-company-copy"},
        h("strong", null, "Loading demo company..."),
        h("p", null, "Preparing the virtual workspace map.")
      )
    );
  }

  const groups = [
    ["Products", company.products || []],
    ["Teams", company.teams || []],
    ["Sources", company.data_sources || []],
  ];

  return h("div", {className: "demo-company-card"},
    h("div", {className: "demo-company-copy"},
      h("span", {className: "demo-company-label"}, "DEMO COMPANY"),
      h("strong", null, company.name),
      h("p", null, company.tagline || company.description),
      h("small", null, company.disclaimer)
    ),
    h("div", {className: "demo-company-groups"},
      groups.map(([label, items]) => h("div", {className: "demo-company-group", key: label},
        h("span", null, label),
        h("div", null, items.slice(0, 6).map((item) => h("code", {key: item}, item)))
      ))
    )
  );
}

function ExplorerSection({title, items, onSelectItem}) {
  return h("div", {className: "explorer-section"},
    h("div", {className: "explorer-section-title"}, title),
    items.length
      ? h("div", {className: "explorer-list"},
          items.slice(0, 5).map((item, idx) => h("button", {
            key: `${title}-${item.id || item.title}-${idx}`,
            className: "explorer-item",
            type: "button",
            title: item.query || item.title,
            onClick: () => onSelectItem(item),
          },
            h("strong", null, item.title),
            h("span", null, item.subtitle || item.meta || ""),
            h("small", null, item.meta || "")
          ))
        )
      : h("div", {className: "explorer-empty"}, "Loading data map...")
  );
}

function Header({runLabel, workspace}) {
  const workspaceName = workspace?.workspace?.name || "OPS-INTEL-V4";
  return h("header", {className: "topbar"},
    h("div", {className: "brand"},
      h("div", {className: "logo-mark"}, "d"),
      h("div", null,
        h("div", {className: "brand-name"}, "deedly"),
        h("div", {className: "brand-subtitle"}, "Customer Ops Intelligence")
      ),
      h("span", {className: "version-pill"}, workspaceName)
    ),
    h("div", {className: "top-actions"},
      h("span", {className: "run-status"}, runLabel),
      h("button", {className: "top-link", type: "button"}, "Resources"),
      h("button", {className: "upgrade-btn neo-btn", type: "button"}, "Upgrade")
    )
  );
}

function Sidebar() {
  return h("aside", {className: "sidebar"},
    h("div", {className: "nav-stack"},
      h("button", {className: "nav-btn neo-btn", type: "button", title: "New session"}, "+"),
      h("button", {className: "nav-btn nav-btn-active neo-btn", type: "button", title: "Chat"}, "◇"),
      h("button", {className: "nav-btn neo-btn", type: "button", title: "Documents"}, "≡")
    ),
    h("div", {className: "avatar"}, "AW")
  );
}

function renderInlineMarkdown(text, keyPrefix) {
  const nodes = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;
  let idx = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(h("strong", {key: `${keyPrefix}-strong-${idx}`}, token.slice(2, -2)));
    } else {
      nodes.push(h("code", {key: `${keyPrefix}-code-${idx}`}, token.slice(1, -1)));
    }

    idx += 1;
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes.length ? nodes : text;
}

function MarkdownText({text}) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks = [];
  let paragraph = [];
  let list = null;

  function flushParagraph() {
    if (!paragraph.length) return;
    const content = paragraph.join("\n").trim();
    if (content) {
      blocks.push(h("p", {key: `p-${blocks.length}`}, renderInlineMarkdown(content, `p-${blocks.length}`)));
    }
    paragraph = [];
  }

  function flushList() {
    if (!list) return;
    const tag = list.type;
    blocks.push(h(tag, {key: `${tag}-${blocks.length}`},
      list.items.map((item, idx) => (
        h("li", {key: `${tag}-item-${idx}`}, renderInlineMarkdown(item, `${tag}-${blocks.length}-${idx}`))
      ))
    ));
    list = null;
  }

  function addListItem(type, content) {
    flushParagraph();
    if (!list || list.type !== type) {
      flushList();
      list = {type, items: []};
    }
    list.items.push(content);
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(h(`h${level}`, {key: `h-${blocks.length}`}, renderInlineMarkdown(heading[2], `h-${blocks.length}`)));
      return;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      flushList();
      blocks.push(h("hr", {key: `hr-${blocks.length}`}));
      return;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      addListItem("ul", unordered[1]);
      return;
    }

    const ordered = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (ordered) {
      addListItem("ol", ordered[1]);
      return;
    }

    paragraph.push(line);
  });

  flushParagraph();
  flushList();

  return h(React.Fragment, null, blocks);
}

function ChatMessage({message, currentRun, selected, onSelectRun}) {
  if (message.sender === "user") {
    return h("div", {className: "message-row user-row"},
      h("div", {className: "user-bubble neo-box"},
        h("div", {className: "message-label"}, "USER"),
        h("div", {className: "message-text"}, message.text)
      )
    );
  }

  const run = message.run || currentRun || emptyRun();
  const status = message.pending ? "● PROCESSING" : message.diagnostic ? "● DIAGNOSTIC" : "● PROCESS COMPLETE";

  return h("div", {
    className: `message-row agent-row ${message.pending ? "is-pending" : ""} ${message.error ? "is-error" : ""} ${message.diagnostic ? "is-diagnostic" : ""} ${selected ? "is-selected" : ""}`,
    onClick: () => onSelectRun?.(run, message.id),
    onKeyDown: (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelectRun?.(run, message.id);
      }
    },
    role: "button",
    tabIndex: 0,
    title: "Select this turn's evidence",
  },
    h("div", {className: "agent-console neo-box"},
      h("div", {className: "console-head"},
        h("span", {className: "console-dot"}),
        h("span", null, "TRACE CONSOLE")
      ),
      (run.tools || []).length
        ? h("ol", {className: "mini-trace"}, (run.tools || []).slice(0, 5).map((tool, idx) => (
            h("li", {key: `${tool}-${idx}`}, tool)
          )))
        : h("div", {className: "console-empty"}, "Awaiting tool calls")
    ),
    h("div", {className: "agent-answer"},
      h("div", {className: "answer-status"}, status),
      h("div", {className: "answer-text markdown-body"}, h(MarkdownText, {text: message.text}))
    )
  );
}

function RightWorkspace({currentRun}) {
  return h("section", {className: "live-workspace"},
    h("div", {className: "workspace-toolbar"},
      h("div", {className: "workspace-title"},
        h("span", {className: "live-dot"}),
        h("span", null, "LIVE WORKSPACE"),
        h("span", {className: "active-pill"}, "ACTIVE DRAFT")
      ),
      h("button", {className: "export-btn", type: "button", title: "Export"}, "↓")
    ),
    h("div", {className: "workspace-scroll"},
      h("div", {className: "workspace-card neo-box"},
        h("div", {className: "doc-header"},
          h("div", null,
            h("div", {className: "doc-kicker"}, "ENTERPRISE CUSTOMER OPS"),
            h("h2", null, "Agent Evidence Brief"),
            currentRun.query ? h("div", {className: "doc-query"}, currentRun.query) : null
          ),
          h("div", {className: "doc-date"}, new Date().toISOString().slice(0, 10))
        ),
        h(Panel, {title: "Tool Trace", items: currentRun.tools || [], ordered: true}),
        h(SourcePanel, {sources: currentRun.sources || []}),
        h(Panel, {title: "KG Paths", items: currentRun.paths || []}),
        h(MemoryPanel, {items: currentRun.memory || []}),
        h(EvalPanel, {data: currentRun.eval || {}})
      )
    )
  );
}

function Panel({title, items, ordered = false}) {
  return h("section", {className: "doc-section"},
    h("h3", null, title),
    items.length
      ? h(ordered ? "ol" : "div", {className: ordered ? "ordered-list" : "card-list"},
          items.map((item, idx) => ordered
            ? h("li", {key: `${item}-${idx}`}, item)
            : h("div", {className: "evidence-card", key: `${item}-${idx}`}, item)
          )
        )
      : h("div", {className: "empty-card"}, title === "RAG Sources" ? "No document citations" : "No data yet")
  );
}

function SourcePanel({sources}) {
  return h("section", {className: "doc-section"},
    h("h3", null, "RAG Sources"),
    sources.length
      ? h("div", {className: "card-list"}, sources.map((source, idx) => (
          h("div", {className: "evidence-card", key: `${source.doc_id}-${idx}`},
            h("strong", null, source.title || "Untitled source"),
            h("span", null, `${source.source_type || "source"} · ${source.doc_id || "unknown"}`),
            h("p", null, source.preview || "")
          )
        )))
      : h("div", {className: "empty-card"}, "No document citations")
  );
}

function MemoryPanel({items}) {
  return h("section", {className: "doc-section"},
    h("h3", null, "Memory"),
    items.length
      ? h("div", {className: "card-list"}, items.map((item, idx) => (
          h("div", {className: "evidence-card", key: `${item.title}-${idx}`},
            h("strong", null, item.title),
            h("p", null, item.body),
            h("span", null, item.meta)
          )
        )))
      : h("div", {className: "empty-card"}, "No memory hits")
  );
}

function EvalPanel({data}) {
  const entries = Object.entries(data);
  return h("section", {className: "doc-section"},
    h("h3", null, "Eval Report"),
    entries.length
      ? h("div", {className: "eval-grid"}, entries.map(([key, value]) => (
          h("div", {className: "metric-card", key},
            h("span", null, key),
            h("strong", null, typeof value === "number" && !Number.isInteger(value) ? value.toFixed(3) : String(value))
          )
        )))
      : h("div", {className: "empty-card"}, "No eval data")
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
