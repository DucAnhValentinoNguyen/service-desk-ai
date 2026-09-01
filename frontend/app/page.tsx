"use client";

import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "/backend";

type User = { id: string; name: string; email: string; role: "owner" | "admin" | "member" | "viewer"; department: string };
type Citation = { title: string; page?: number; excerpt: string };
type Proposal = { id: string; request_id: string; action_type: string; risk: string; status: string; payload: Record<string, unknown>; approval?: { id: string; status: string } };
type RequestItem = { id: string; content: string; status: string; category: string; rationale: string; assigned_agent?: string; answer?: string; citations: Citation[]; ticket?: { id: string }; proposals?: Proposal[] };
type Approval = { id: string; status: string; decided_by?: string; note?: string; proposal: Proposal };
type KnowledgeAnswer = { answer: string; grounded: boolean; confidence: number; citations: Citation[]; warning?: string; escalation?: { ticket_id: string } };
type IntakeResult = { kind: "knowledge" | "request"; route: { category: string; confidence: number; rationale: string }; knowledge?: KnowledgeAnswer; request?: RequestItem };
type PlatformOverview = {
  available: boolean;
  run_id?: string;
  knowledge_stats?: { documents: number; chunks: number };
  top_risky_devices?: Array<{ device_id: string; gateway_id: string; risk_score: number; anomalies: string[] }>;
};
type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  tone?: "grounded" | "abstained" | "request";
  label: string;
  content: string;
  confidence?: number;
  citations?: Citation[];
  note?: string;
};

const PROMPTS = [
  "What should an operator check when a purchase order is late?",
  "Customer reports that her room sensor stopped sending temperature readings.",
  "Which devices need proactive support attention because of low battery or weak signal?",
];

function displayRole(user: User) {
  if (user.role === "owner") return "IT administrator";
  if (user.role === "admin") return `${user.department} specialist`;
  return user.role === "member" ? "Staff member" : "Customer";
}

function assistantMessageFromResult(result: IntakeResult): ChatMessage | null {
  if (result.kind === "knowledge" && result.knowledge) {
    return {
      id: `assistant-${crypto.randomUUID()}`,
      role: "assistant",
      tone: result.knowledge.grounded ? "grounded" : "abstained",
      label: result.knowledge.grounded ? "Grounded answer" : "Safe refusal",
      content: result.knowledge.answer,
      confidence: result.knowledge.confidence,
      citations: result.knowledge.citations,
      note: result.knowledge.escalation ? `Human-review ticket created: ${result.knowledge.escalation.ticket_id}` : result.knowledge.warning,
    };
  }
  if (result.request) {
    const request = result.request;
    return {
      id: `assistant-${crypto.randomUUID()}`,
      role: "assistant",
      tone: "request",
      label: "Tracked request",
      content: request.answer || `Created ${request.ticket?.id || request.id} with status ${request.status.replaceAll("_", " ")}.`,
      confidence: result.route.confidence,
      citations: request.citations,
      note: `Category: ${request.category.replaceAll("_", " ")}. ${request.proposals?.length ? "Protected action proposal prepared for review." : request.rationale}`,
    };
  }
  return null;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [demoUsers, setDemoUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("duc-anh@example.com");
  const [password, setPassword] = useState("demo123");
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<RequestItem | null>(null);
  const [content, setContent] = useState("");
  const [platform, setPlatform] = useState<PlatformOverview | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  const headers: Record<string, string> = user ? { "x-demo-user": user.id, "x-workspace-id": "demo-workspace" } : {};

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
    return response.json() as Promise<T>;
  }

  async function refresh() {
    if (!user) return;
    try {
      const [nextRequests, nextApprovals, nextPlatform] = await Promise.all([
        api<RequestItem[]>("/v1/requests"),
        api<Approval[]>("/v1/approvals"),
        api<PlatformOverview>("/v1/platform/overview").catch(() => ({ available: false })),
      ]);
      setRequests(nextRequests);
      setApprovals(nextApprovals);
      setPlatform(nextPlatform);
    } catch (err) {
      setError(err instanceof Error ? err.message : "API unavailable");
    }
  }

  useEffect(() => {
    void fetch(`${API}/v1/auth/demo-users`).then((response) => response.json()).then(setDemoUsers).catch(() => setError("API unavailable"));
  }, []);

  useEffect(() => {
    void refresh();
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setMessages([]);
      setUser(await api<User>("/v1/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, password }) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleIntake() {
    if (!content.trim() || !user || busy) return;
    const question = content.trim();
    const userMessage: ChatMessage = {
      id: `user-${crypto.randomUUID()}`,
      role: "user",
      label: "You",
      content: question,
    };
    setMessages((current) => [...current, userMessage]);
    setContent("");
    setBusy(true);
    setError("");
    try {
      const result = await api<IntakeResult>("/v1/intake", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: question }),
      });
      const assistant = assistantMessageFromResult(result);
      if (assistant) {
        setMessages((current) => [...current, assistant]);
      }
      if (result.kind === "knowledge") {
        setSelected(null);
      } else if (result.request) {
        setSelected(result.request);
      }
      await refresh();
    } catch (err) {
      const fallback: ChatMessage = {
        id: `assistant-${crypto.randomUUID()}`,
        role: "assistant",
        tone: "abstained",
        label: "System error",
        content: err instanceof Error ? err.message : "Could not process intake.",
      };
      setMessages((current) => [...current, fallback]);
      setError(err instanceof Error ? err.message : "Could not process intake");
    } finally {
      setBusy(false);
    }
  }

  async function selectRequest(item: RequestItem) {
    try {
      setSelected(await api<RequestItem>(`/v1/requests/${item.id}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load request");
    }
  }

  async function decide(approval: Approval, decision: "approve" | "reject") {
    setBusy(true);
    setError("");
    try {
      await api(`/v1/approvals/${approval.id}/${decision}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ note: "Reviewed by IT administrator in the demo console" }),
      });
      await refresh();
      setSelected(await api<RequestItem>(`/v1/requests/${approval.proposal.request_id}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval decision failed");
    } finally {
      setBusy(false);
    }
  }

  function handleComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleIntake();
    }
  }

  if (!user) {
    return <main className="login-shell"><section className="login-card"><div className="brand"><span className="brand-mark">SD</span><div><strong>SERVICE DESK AI</strong><small>SECURE DEMO ENVIRONMENT</small></div></div><p className="eyebrow">ROLE-BASED ACCESS</p><h1>Sign in to your<br /><em>workspace.</em></h1><p className="lede">Staff and customers see only their own requests. Specialists see their assigned domain. IT administration has full oversight.</p><form onSubmit={login}><label>Email<input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required /></label><label>Password<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required /></label><button className="primary wide" disabled={busy}>{busy ? "Signing in..." : "Sign in"} <span className="button-arrow">{"\u2197"}</span></button></form>{error && <div className="error">{error}</div>}<div className="demo-identities"><b>Demo accounts / password: demo123</b>{demoUsers.map((item) => <button type="button" key={item.id} onClick={() => { setEmail(item.email); setPassword("demo123"); }}><span>{item.name}</span><small>{displayRole(item)}</small></button>)}</div></section></main>;
  }

  const pending = approvals.filter((item) => item.status === "pending");
  const approvalForRequest = (requestId: string) => approvals.find((item) => item.proposal.request_id === requestId);
  const riskyCount = platform?.top_risky_devices?.length || 0;

  return <main className="shell"><header className="topbar"><div className="brand"><span className="brand-mark">SD</span><div><strong>SERVICE DESK AI</strong><small>OPERATIONS CONTROL</small></div></div><div className="identity"><span className="live-dot" /> {user.name} <span className="identity-divider" /> {displayRole(user)} <button className="logout" onClick={() => { setUser(null); setSelected(null); setRequests([]); setApprovals([]); setMessages([]); setPlatform(null); }}>Sign out</button></div></header><nav className="tabs"><button className="active">Inbox{pending.length > 0 && <i>{pending.length}</i>}</button></nav>{error && <div className="error" role="alert">{error}</div>}
    <section className="content-grid chat-layout">
      <div className="panel chat-panel">
        <div className="panel-title">
          <div><span className="section-no">01 / AI DESK</span><h2>Operational chat</h2></div>
          <span className={`mode-pill ${platform?.available ? "" : "orange"}`}>{platform?.available ? `RUN ${platform.run_id}` : "LOCAL ONLY"}</span>
        </div>
        <div className="platform-inline">
          <span className="platform-inline-copy">{platform?.available ? `Connected to the latest platform run. ${platform.knowledge_stats?.documents || 0} platform documents indexed.` : "Running without linked platform artifacts. The local knowledge base is still available."}</span>
          {platform?.available && riskyCount > 0 && (platform.top_risky_devices || []).slice(0, 3).map((device) => <span className="platform-chip" key={device.device_id}>{device.device_id} / {device.gateway_id} / {Math.round(device.risk_score * 100)}%</span>)}
        </div>
        <div className="chat-transcript">
          {!messages.length && <div className="chat-empty"><span className="section-no">READY</span><h3>Ask a policy question, report an issue, or query the latest pipeline run.</h3><p>The conversation stays visible like a chat, so you can keep track of what you asked and how the assistant responded.</p></div>}
          {messages.map((message) => <article key={message.id} className={`chat-message ${message.role} ${message.tone || ""}`}><div className="message-meta"><span>{message.label}</span>{message.confidence !== undefined && <span>{Math.round(message.confidence * 100)}% confidence</span>}</div><p>{message.content}</p>{message.note && <small className="message-note">{message.note}</small>}{message.citations && message.citations.length > 0 && <Citations citations={message.citations} />}</article>)}
          <div ref={transcriptEndRef} />
        </div>
        <div className="composer-shell">
          <textarea value={content} onChange={(event) => setContent(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="Ask a policy question, report an issue, or request a technician appointment..." />
          <div className="composer-bottom"><span>Press Enter to send. Use Shift+Enter for a new line.</span><button className="primary" disabled={busy || !content.trim()} onClick={() => void handleIntake()}>{busy ? "Working..." : "Send to AI"}<span className="button-arrow">{"\u2197"}</span></button></div>
          <div className="demo-prompts">{PROMPTS.map((prompt) => <button key={prompt} onClick={() => setContent(prompt)}>{prompt.includes("low battery") ? "Ask platform RAG" : prompt.includes("room sensor") ? "Customer support" : "Ask a policy"}</button>)}</div>
        </div>
      </div>
      <aside className="panel safety-panel"><span className="section-no">ACCESS CONTROL</span><h2>{displayRole(user)}<br /><em>session active.</em></h2><div className="safety-line"><b>01</b><span>Minimum visibility</span><small>{user.role === "owner" ? "Full operational oversight." : user.role === "admin" ? "Assigned domain only." : "Own requests only."}</small></div><div className="safety-line"><b>02</b><span>Protected actions</span><small>Only IT administration can approve writes.</small></div><div className="safety-line"><b>03</b><span>Evidence first</span><small>Answers cite approved documents or refuse unsafe prompts.</small></div></aside>
    </section>
    <section className="content-grid queue-detail"><div className="panel table-panel"><div className="panel-title"><div><span className="section-no">02 / INBOX</span><h2>All requests and tickets</h2><small className="queue-caption">Active work, completed tickets, and approval decisions in one queue.</small></div><button className="quiet" onClick={() => void refresh()}>Refresh</button></div><div className="request-list">{requests.map((item) => { const approval = approvalForRequest(item.id); return <button className={`request-row selectable ${selected?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => void selectRequest(item)}><span className={`category ${item.category}`}>{item.category.replace("_", " ")}</span><div className="request-main"><strong>{item.content}</strong><small>{item.ticket?.id || item.id} / {item.status.replaceAll("_", " ")}</small></div><span className={`status ${approval ? `approval-${approval.status}` : item.status}`}>{approval ? `approval ${approval.status}` : item.status.replaceAll("_", " ")}</span></button>; })}{!requests.length && <div className="empty">No visible requests yet.</div>}</div></div><RequestDetail item={selected} approval={selected ? approvalForRequest(selected.id) : undefined} onDecide={decide} busy={busy} canDecide={user.role === "owner"} /></section><footer><span>DEMO DATA IS STORED IN SQLITE + AI DATA PLATFORM</span><span>PROPOSE. APPROVE. AUDIT.</span></footer></main>;
}

function Citations({ citations }: { citations: Citation[] }) {
  return citations.length ? <div className="citations">{citations.map((citation, index) => <div key={`${citation.title}-${index}`}><b>[{index + 1}] {citation.title}{citation.page ? ` / section ${citation.page}` : ""}</b><small>{citation.excerpt}</small></div>)}</div> : null;
}

function RequestDetail({ item, approval, onDecide, busy, canDecide }: { item: RequestItem | null; approval?: Approval; onDecide: (approval: Approval, decision: "approve" | "reject") => void; busy: boolean; canDecide: boolean }) {
  if (!item) return <aside className="panel detail-panel"><span className="section-no">03 / REQUEST DETAIL</span><h2>Select a request</h2><p className="muted">Select any active or finished request to inspect its route, evidence, ticket, and approval history.</p></aside>;
  return <aside className="panel detail-panel"><span className="section-no">03 / REQUEST DETAIL</span><span className={`status ${item.status}`}>{item.status.replaceAll("_", " ")}</span><h2>{item.ticket?.id || item.id}</h2><p className="detail-request">{item.content}</p><p className="muted">Routed to {item.assigned_agent || "human review"}: {item.rationale}</p>{item.answer && <><b className="detail-label">AI RESPONSE</b><p className="detail-answer">{item.answer}</p><Citations citations={item.citations} /></>}{item.proposals?.map((proposal) => <div className="detail-proposal" key={proposal.id}><b className="detail-label">PROPOSED ACTION</b><strong>{proposal.action_type.replaceAll("_", " ")}</strong><p>{String(proposal.payload.ai_draft || proposal.payload.draft || proposal.payload.reason || "Protected action prepared for IT review.")}</p><code className="detail-payload">{JSON.stringify(proposal.payload, null, 2)}</code>{canDecide && approval?.status === "pending" ? <div className="approval-actions"><button className="reject" disabled={busy} onClick={() => onDecide(approval, "reject")}>Reject</button><button className="approve" disabled={busy} onClick={() => onDecide(approval, "approve")}>Approve and execute</button></div> : <small>{approval?.status === "approved" ? "Approved and executed in the simulator." : approval?.status === "rejected" ? "Rejected. No external change was made." : canDecide ? "Awaiting IT administrator approval." : "Approval review is restricted to the IT administrator."}</small>}</div>)}</aside>;
}
