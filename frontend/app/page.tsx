"use client";

import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "/backend";

type User = { id: string; name: string; email: string; role: "owner" | "admin" | "member" | "viewer"; department: string };
type Citation = { title: string; page?: number; excerpt: string };
type Proposal = { id: string; request_id: string; action_type: string; risk: string; status: string; payload: Record<string, unknown>; approval?: { id: string; status: string } };
type RequestItem = { id: string; content: string; status: string; category: string; rationale: string; assigned_agent?: string; answer?: string; citations: Citation[]; ticket?: { id: string }; proposals?: Proposal[] };
type Approval = { id: string; status: string; decided_by?: string; note?: string; proposal: Proposal };
type PlatformOverview = {
  available: boolean;
  run_id?: string;
  knowledge_stats?: { documents: number; chunks: number };
  top_risky_devices?: Array<{ device_id: string; gateway_id: string; risk_score: number; anomalies: string[] }>;
};
type ChatMessage = {
  id: string;
  conversation_id: string;
  workspace_id: string;
  role: "user" | "assistant";
  label: string;
  tone?: "grounded" | "abstained" | "request" | null;
  content: string;
  confidence?: number | null;
  citations: Citation[];
  note?: string | null;
  related_request_id?: string | null;
  created_at?: string;
};
type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
};
type Conversation = ConversationSummary & { messages: ChatMessage[] };
type KnowledgeAnswer = { answer: string; grounded: boolean; confidence: number; citations: Citation[]; warning?: string; escalation?: { ticket_id: string; request_id?: string } };
type IntakeResult = { kind: "knowledge" | "request"; route: { category: string; confidence: number; rationale: string }; knowledge?: KnowledgeAnswer; request?: RequestItem };
type ChatResponse = {
  conversation: Conversation;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  result: IntakeResult;
};

const PROMPTS = [
  { label: "Ask a policy", content: "What should an operator check when a purchase order is late?" },
  { label: "Customer support", content: "Customer reports that her room sensor stopped sending temperature readings." },
  { label: "Ask platform RAG", content: "Which devices need proactive support attention because of low battery or weak signal?" },
];

function displayRole(user: User) {
  if (user.role === "owner") return "IT administrator";
  if (user.role === "admin") return `${user.department} specialist`;
  return user.role === "member" ? "Staff member" : "Customer";
}

function formatTimestamp(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function summarizeConversation(conversation: Conversation): ConversationSummary {
  return {
    id: conversation.id,
    title: conversation.title,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    message_count: conversation.message_count,
    last_message_preview: conversation.last_message_preview,
  };
}

function upsertConversation(list: ConversationSummary[], summary: ConversationSummary) {
  return [summary, ...list.filter((item) => item.id !== summary.id)].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [error, setError] = useState("");
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  const headers: Record<string, string> = user ? { "x-demo-user": user.id, "x-workspace-id": "demo-workspace" } : {};
  const activeConversation = conversations.find((item) => item.id === activeConversationId) || null;

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loadingConversation]);

  async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
    return response.json() as Promise<T>;
  }

  async function refreshWorkspace(preferredConversationId?: string | null) {
    if (!user) return;
    try {
      const [nextRequests, nextApprovals, nextPlatform, nextConversations] = await Promise.all([
        api<RequestItem[]>("/v1/requests"),
        api<Approval[]>("/v1/approvals"),
        api<PlatformOverview>("/v1/platform/overview").catch(() => ({ available: false })),
        api<ConversationSummary[]>("/v1/conversations"),
      ]);
      setRequests(nextRequests);
      setApprovals(nextApprovals);
      setPlatform(nextPlatform);
      setConversations(nextConversations);
      const nextConversationId = preferredConversationId === undefined ? (activeConversationId || nextConversations[0]?.id || null) : (preferredConversationId || nextConversations[0]?.id || null);
      if (nextConversationId) {
        await loadConversation(nextConversationId);
      } else {
        setActiveConversationId(null);
        setMessages([]);
        setSelected(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "API unavailable");
    }
  }

  async function loadConversation(conversationId: string) {
    if (!user) return;
    setLoadingConversation(true);
    try {
      const conversation = await api<Conversation>(`/v1/conversations/${conversationId}`);
      setActiveConversationId(conversation.id);
      setMessages(conversation.messages);
      const relatedRequestId = [...conversation.messages].reverse().find((message) => message.related_request_id)?.related_request_id;
      if (relatedRequestId) {
        try {
          setSelected(await api<RequestItem>(`/v1/requests/${relatedRequestId}`));
        } catch {
          setSelected(null);
        }
      } else {
        setSelected(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load conversation");
    } finally {
      setLoadingConversation(false);
    }
  }

  useEffect(() => {
    void fetch(`${API}/v1/auth/demo-users`).then((response) => response.json()).then(setDemoUsers).catch(() => setError("API unavailable"));
  }, []);

  useEffect(() => {
    if (user) {
      void refreshWorkspace(null);
    }
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setMessages([]);
      setConversations([]);
      setActiveConversationId(null);
      setSelected(null);
      setUser(await api<User>("/v1/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, password }) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  async function startConversation() {
    if (!user || busy) return;
    setBusy(true);
    setError("");
    try {
      const conversation = await api<Conversation>("/v1/conversations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: "New chat" }),
      });
      setConversations((current) => upsertConversation(current, summarizeConversation(conversation)));
      setActiveConversationId(conversation.id);
      setMessages([]);
      setSelected(null);
      setContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start a new chat");
    } finally {
      setBusy(false);
    }
  }

  async function streamAssistantMessage(message: ChatMessage) {
    const typingId = message.id;
    const tokens = message.content.split(/(\s+)/).filter(Boolean);
    setMessages((current) => [...current, { ...message, content: "", citations: [], note: null }]);
    let built = "";
    const chunkSize = tokens.length > 80 ? 4 : tokens.length > 40 ? 3 : 2;
    for (let index = 0; index < tokens.length; index += chunkSize) {
      built += tokens.slice(index, index + chunkSize).join("");
      setMessages((current) => current.map((item) => item.id === typingId ? { ...item, content: built } : item));
      await wait(tokens.length > 80 ? 20 : 32);
    }
    setMessages((current) => current.map((item) => item.id === typingId ? message : item));
  }

  async function handleIntake() {
    if (!content.trim() || !user || busy) return;
    const question = content.trim();
    const optimisticUser: ChatMessage = {
      id: `temp-user-${crypto.randomUUID()}`,
      conversation_id: activeConversationId || "pending",
      workspace_id: "demo-workspace",
      role: "user",
      label: "You",
      content: question,
      citations: [],
    };
    setMessages((current) => [...current, optimisticUser]);
    setContent("");
    setBusy(true);
    setError("");
    try {
      const response = await api<ChatResponse>("/v1/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: question, conversation_id: activeConversationId || undefined }),
      });
      setActiveConversationId(response.conversation.id);
      setConversations((current) => upsertConversation(current, summarizeConversation(response.conversation)));
      setMessages((current) => current.map((item) => item.id === optimisticUser.id ? response.user_message : item));
      await streamAssistantMessage(response.assistant_message);
      if (response.result.kind === "request" && response.result.request) {
        setSelected(response.result.request);
      } else if (response.result.kind === "knowledge" && response.result.knowledge?.escalation?.request_id) {
        try {
          setSelected(await api<RequestItem>(`/v1/requests/${response.result.knowledge.escalation.request_id}`));
        } catch {
          setSelected(null);
        }
      } else {
        setSelected(null);
      }
      const [nextRequests, nextApprovals, nextPlatform, nextConversations] = await Promise.all([
        api<RequestItem[]>("/v1/requests"),
        api<Approval[]>("/v1/approvals"),
        api<PlatformOverview>("/v1/platform/overview").catch(() => ({ available: false })),
        api<ConversationSummary[]>("/v1/conversations"),
      ]);
      setRequests(nextRequests);
      setApprovals(nextApprovals);
      setPlatform(nextPlatform);
      setConversations(nextConversations);
    } catch (err) {
      setMessages((current) => current.map((item) => item.id === optimisticUser.id ? { ...optimisticUser, id: `user-${crypto.randomUUID()}` } : item).concat({
        id: `assistant-${crypto.randomUUID()}`,
        conversation_id: activeConversationId || "local",
        workspace_id: "demo-workspace",
        role: "assistant",
        label: "System error",
        tone: "abstained",
        content: err instanceof Error ? err.message : "Could not process intake.",
        citations: [],
      }));
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
      if (activeConversationId) {
        await refreshWorkspace(activeConversationId);
      } else {
        await refreshWorkspace(null);
      }
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

  return <main className="shell shell-wide"><header className="topbar"><div className="brand"><span className="brand-mark">SD</span><div><strong>SERVICE DESK AI</strong><small>OPERATIONS CONTROL</small></div></div><div className="identity"><span className="live-dot" /> {user.name} <span className="identity-divider" /> {displayRole(user)} <button className="logout" onClick={() => { setUser(null); setSelected(null); setRequests([]); setApprovals([]); setMessages([]); setPlatform(null); setConversations([]); setActiveConversationId(null); }}>Sign out</button></div></header><nav className="tabs"><button className="active">Inbox{pending.length > 0 && <i>{pending.length}</i>}</button></nav>{error && <div className="error" role="alert">{error}</div>}
    <section className="workspace-layout">
      <aside className="panel sidebar-panel">
        <div className="sidebar-head">
          <div><span className="section-no">01 / CHATS</span><h2>Conversations</h2></div>
          <button className="quiet" onClick={() => void startConversation()} disabled={busy}>New chat</button>
        </div>
        <div className="sidebar-platform">
          <span className="section-no">{platform?.available ? "PLATFORM ONLINE" : "LOCAL MODE"}</span>
          <strong>{platform?.available ? `Run ${platform.run_id}` : "Service-desk knowledge only"}</strong>
          <small>{platform?.available ? `${platform.knowledge_stats?.documents || 0} platform documents, ${(platform.top_risky_devices || []).length} high-risk devices surfaced.` : "The app can still answer from the local knowledge base and workflow policies."}</small>
        </div>
        <div className="conversation-list">
          {conversations.map((conversation) => <button key={conversation.id} className={`conversation-row ${conversation.id === activeConversationId ? "active" : ""}`} onClick={() => void loadConversation(conversation.id)} disabled={busy || loadingConversation}><strong>{conversation.title}</strong><span className="conversation-preview">{conversation.last_message_preview || "No messages yet."}</span><span className="conversation-meta">{conversation.message_count} messages / {formatTimestamp(conversation.updated_at)}</span></button>)}
          {!conversations.length && <div className="empty sidebar-empty">No conversations yet. Start a new chat.</div>}
        </div>
        <div className="sidebar-guardrails">
          <span className="section-no">GUARDRAILS</span>
          <small>Unsafe prompts are refused. Protected actions still require approval. Answers stay grounded in approved evidence.</small>
        </div>
      </aside>
      <section className="panel chat-main">
        <div className="chat-panel-head">
          <div><span className="section-no">02 / AI DESK</span><h2>{activeConversation?.title || "New chat"}</h2></div>
          <span className={`mode-pill ${platform?.available ? "" : "orange"}`}>{platform?.available ? `RUN ${platform.run_id}` : "LOCAL ONLY"}</span>
        </div>
        <div className="platform-inline">
          <span className="platform-inline-copy">{platform?.available ? `Connected to the latest platform run. Ask about documents, risky devices, or support guidance without leaving the chat.` : "Running without linked platform artifacts. The local knowledge base is still available."}</span>
        </div>
        <div className="chat-transcript">
          {!messages.length && !loadingConversation && <div className="chat-empty"><span className="section-no">READY</span><h3>Ask a policy question, report an issue, or query the latest pipeline run.</h3><p>Your full conversation stays visible in one thread, and past chats stay in the sidebar.</p></div>}
          {loadingConversation && <div className="chat-empty"><span className="section-no">LOADING</span><h3>Opening conversation...</h3></div>}
          {messages.map((message) => <article key={message.id} className={`chat-message ${message.role} ${message.tone || ""}`}><div className="message-meta"><span>{message.label}</span>{message.confidence !== undefined && message.confidence !== null && <span>{Math.round(message.confidence * 100)}% confidence</span>}</div><p>{message.content || <span className="typing-dots"><i /><i /><i /></span>}</p>{message.note && <small className="message-note">{message.note}</small>}{message.citations.length > 0 && <Citations citations={message.citations} />}</article>)}
          <div ref={transcriptEndRef} />
        </div>
        <div className="composer-shell">
          <textarea value={content} onChange={(event) => setContent(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="Ask a policy question, report an issue, or request a technician appointment..." />
          <div className="composer-bottom"><span>Enter sends. Shift+Enter adds a new line.</span><button className="primary" disabled={busy || !content.trim()} onClick={() => void handleIntake()}>{busy ? "Working..." : "Send to AI"}<span className="button-arrow">{"\u2197"}</span></button></div>
          <div className="demo-prompts">{PROMPTS.map((prompt) => <button key={prompt.label} onClick={() => setContent(prompt.content)}>{prompt.label}</button>)}</div>
        </div>
      </section>
    </section>
    <section className="content-grid queue-detail"><div className="panel table-panel"><div className="panel-title"><div><span className="section-no">03 / INBOX</span><h2>All requests and tickets</h2><small className="queue-caption">Active work, completed tickets, and approval decisions in one queue.</small></div><button className="quiet" onClick={() => void refreshWorkspace(activeConversationId)}>Refresh</button></div><div className="request-list">{requests.map((item) => { const approval = approvalForRequest(item.id); return <button className={`request-row selectable ${selected?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => void selectRequest(item)}><span className={`category ${item.category}`}>{item.category.replace("_", " ")}</span><div className="request-main"><strong>{item.content}</strong><small>{item.ticket?.id || item.id} / {item.status.replaceAll("_", " ")}</small></div><span className={`status ${approval ? `approval-${approval.status}` : item.status}`}>{approval ? `approval ${approval.status}` : item.status.replaceAll("_", " ")}</span></button>; })}{!requests.length && <div className="empty">No visible requests yet.</div>}</div></div><RequestDetail item={selected} approval={selected ? approvalForRequest(selected.id) : undefined} onDecide={decide} busy={busy} canDecide={user.role === "owner"} /></section><footer><span>DEMO DATA IS STORED IN SQLITE + AI DATA PLATFORM</span><span>CHAT. APPROVE. AUDIT.</span></footer></main>;
}

function Citations({ citations }: { citations: Citation[] }) {
  return <div className="citations">{citations.map((citation, index) => <div key={`${citation.title}-${index}`}><b>[{index + 1}] {citation.title}{citation.page ? ` / section ${citation.page}` : ""}</b><small>{citation.excerpt}</small></div>)}</div>;
}

function RequestDetail({ item, approval, onDecide, busy, canDecide }: { item: RequestItem | null; approval?: Approval; onDecide: (approval: Approval, decision: "approve" | "reject") => void; busy: boolean; canDecide: boolean }) {
  if (!item) return <aside className="panel detail-panel"><span className="section-no">04 / REQUEST DETAIL</span><h2>Select a request</h2><p className="muted">Select any active or finished request to inspect its route, evidence, ticket, and approval history.</p></aside>;
  return <aside className="panel detail-panel"><span className="section-no">04 / REQUEST DETAIL</span><span className={`status ${item.status}`}>{item.status.replaceAll("_", " ")}</span><h2>{item.ticket?.id || item.id}</h2><p className="detail-request">{item.content}</p><p className="muted">Routed to {item.assigned_agent || "human review"}: {item.rationale}</p>{item.answer && <><b className="detail-label">AI RESPONSE</b><p className="detail-answer">{item.answer}</p><Citations citations={item.citations} /></>}{item.proposals?.map((proposal) => <div className="detail-proposal" key={proposal.id}><b className="detail-label">PROPOSED ACTION</b><strong>{proposal.action_type.replaceAll("_", " ")}</strong><p>{String(proposal.payload.ai_draft || proposal.payload.draft || proposal.payload.reason || "Protected action prepared for IT review.")}</p><code className="detail-payload">{JSON.stringify(proposal.payload, null, 2)}</code>{canDecide && approval?.status === "pending" ? <div className="approval-actions"><button className="reject" disabled={busy} onClick={() => onDecide(approval, "reject")}>Reject</button><button className="approve" disabled={busy} onClick={() => onDecide(approval, "approve")}>Approve and execute</button></div> : <small>{approval?.status === "approved" ? "Approved and executed in the simulator." : approval?.status === "rejected" ? "Rejected. No external change was made." : canDecide ? "Awaiting IT administrator approval." : "Approval review is restricted to the IT administrator."}</small>}</div>)}</aside>;
}
