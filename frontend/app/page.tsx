"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

type User = { id: string; name: string; email: string; role: "owner" | "admin" | "member" | "viewer"; department: string };
type Citation = { title: string; page?: number; excerpt: string };
type Proposal = { id: string; request_id: string; action_type: string; risk: string; status: string; payload: Record<string, unknown>; approval?: { id: string; status: string } };
type RequestItem = { id: string; content: string; status: string; category: string; rationale: string; assigned_agent?: string; answer?: string; citations: Citation[]; ticket?: { id: string }; proposals?: Proposal[] };
type Approval = { id: string; status: string; decided_by?: string; note?: string; proposal: Proposal };
type KnowledgeAnswer = { answer: string; grounded: boolean; confidence: number; citations: Citation[]; escalation?: { ticket_id: string } };

function displayRole(user: User) {
  if (user.role === "owner") return "IT administrator";
  if (user.role === "admin") return `${user.department} specialist`;
  return user.role === "member" ? "Staff member" : "Customer";
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [demoUsers, setDemoUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("duc-anh@example.com");
  const [password, setPassword] = useState("demo123");
  const [tab, setTab] = useState<"inbox" | "approvals">("inbox");
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<RequestItem | null>(null);
  const [content, setContent] = useState("");
  const [knowledge, setKnowledge] = useState<KnowledgeAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const headers: Record<string, string> = user ? { "x-demo-user": user.id, "x-workspace-id": "demo-workspace" } : {};
  async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
    return response.json() as Promise<T>;
  }
  async function refresh() {
    if (!user) return;
    try {
      const [nextRequests, nextApprovals] = await Promise.all([api<RequestItem[]>("/v1/requests"), api<Approval[]>("/v1/approvals")]);
      setRequests(nextRequests); setApprovals(nextApprovals);
    } catch (err) { setError(err instanceof Error ? err.message : "API unavailable"); }
  }
  useEffect(() => { void fetch(`${API}/v1/auth/demo-users`).then((response) => response.json()).then(setDemoUsers).catch(() => setError("API unavailable")); }, []);
  useEffect(() => { void refresh(); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  async function login(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { setUser(await api<User>("/v1/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, password }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Login failed"); }
    finally { setBusy(false); }
  }
  async function submitRequest() {
    if (!content.trim() || !user) return;
    setBusy(true); setError(""); setKnowledge(null);
    try { const created = await api<RequestItem>("/v1/requests", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ content }) }); setContent(""); setSelected(created); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not process request"); }
    finally { setBusy(false); }
  }
  async function askKnowledge() {
    if (!content.trim() || !user) return;
    setBusy(true); setError("");
    try { setKnowledge(await api<KnowledgeAnswer>("/v1/knowledge/query", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: content, answer_mode: "explain" }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Knowledge search failed"); }
    finally { setBusy(false); }
  }
  async function selectRequest(item: RequestItem) {
    try { setSelected(await api<RequestItem>(`/v1/requests/${item.id}`)); setKnowledge(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not load request"); }
  }
  async function decide(approval: Approval, decision: "approve" | "reject") {
    setBusy(true); setError("");
    try { await api(`/v1/approvals/${approval.id}/${decision}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ note: "Reviewed by IT administrator in the demo console" }) }); await refresh(); setSelected(await api<RequestItem>(`/v1/requests/${approval.proposal.request_id}`)); setTab("inbox"); }
    catch (err) { setError(err instanceof Error ? err.message : "Approval decision failed"); }
    finally { setBusy(false); }
  }

  if (!user) return <main className="login-shell"><section className="login-card"><div className="brand"><span className="brand-mark">SD</span><div><strong>SERVICE DESK AI</strong><small>SECURE DEMO ENVIRONMENT</small></div></div><p className="eyebrow">ROLE-BASED ACCESS</p><h1>Sign in to your<br /><em>workspace.</em></h1><p className="lede">Staff and customers see only their own requests. Specialists see their assigned domain. IT administration has full oversight.</p><form onSubmit={login}><label>Email<input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required /></label><label>Password<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required /></label><button className="primary wide" disabled={busy}>{busy ? "Signing in..." : "Sign in"} <b>-&gt;</b></button></form>{error && <div className="error">{error}</div>}<div className="demo-identities"><b>Demo accounts / password: demo123</b>{demoUsers.map((item) => <button type="button" key={item.id} onClick={() => { setEmail(item.email); setPassword("demo123"); }}><span>{item.name}</span><small>{displayRole(item)}</small></button>)}</div></section></main>;

  const pending = approvals.filter((item) => item.status === "pending");
  return <main className="shell"><header className="topbar"><div className="brand"><span className="brand-mark">SD</span><div><strong>SERVICE DESK AI</strong><small>OPERATIONS CONTROL</small></div></div><div className="identity"><span className="live-dot" /> {user.name} <span className="identity-divider" /> {displayRole(user)} <button className="logout" onClick={() => { setUser(null); setSelected(null); setRequests([]); setApprovals([]); }}>Sign out</button></div></header><nav className="tabs"><button className={tab === "inbox" ? "active" : ""} onClick={() => setTab("inbox")}>Inbox</button>{user.role === "owner" && <button className={tab === "approvals" ? "active" : ""} onClick={() => setTab("approvals")}>Approvals{pending.length > 0 && <i>{pending.length}</i>}</button>}</nav>{error && <div className="error" role="alert">{error}</div>}
    {tab === "inbox" && <><section className="content-grid"><div className="panel request-panel"><div className="panel-title"><div><span className="section-no">01 / INTAKE</span><h2>New request</h2></div><span className="mode-pill">ROUTER ONLINE</span></div><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="Ask a policy question, report an issue, or request a technician appointment..." /><div className="composer-foot"><span>Ask searches approved knowledge. Submit creates a tracked ticket.</span><div className="button-pair"><button className="quiet" disabled={busy} onClick={() => void askKnowledge()}>Ask knowledge</button><button className="primary" disabled={busy} onClick={() => void submitRequest()}>{busy ? "Working..." : "Submit request"}<b>-&gt;</b></button></div></div><div className="demo-prompts"><button onClick={() => setContent("What should an operator check when a purchase order is late?")}>Ask a policy</button><button onClick={() => setContent("Customer reports that her room sensor stopped sending temperature readings.")}>Customer support</button><button onClick={() => setContent("I need to book a technician appointment for next week.")}>Book appointment</button></div></div><aside className="panel safety-panel"><span className="section-no">ACCESS CONTROL</span><h2>{displayRole(user)}<br /><em>session active.</em></h2><div className="safety-line"><b>01</b><span>Minimum visibility</span><small>{user.role === "owner" ? "Full operational oversight." : user.role === "admin" ? "Assigned domain only." : "Own requests only."}</small></div><div className="safety-line"><b>02</b><span>Protected actions</span><small>Only IT administration can approve writes.</small></div><div className="safety-line"><b>03</b><span>Evidence first</span><small>Answers cite approved documents or abstain.</small></div></aside></section>{knowledge && <section className="panel answer"><div className="answer-head"><span className={knowledge.grounded ? "grounded" : "abstained"}>{knowledge.grounded ? "GROUNDED ANSWER" : "INSUFFICIENT EVIDENCE"}</span><span>{Math.round(knowledge.confidence * 100)}% confidence</span></div><p>{knowledge.answer}</p>{knowledge.escalation && <small>Human-review ticket created: {knowledge.escalation.ticket_id}</small>}<Citations citations={knowledge.citations} /></section>}<section className="content-grid queue-detail"><div className="panel table-panel"><div className="panel-title"><div><span className="section-no">02 / WORK QUEUE</span><h2>Requests and tickets</h2></div><button className="quiet" onClick={() => void refresh()}>Refresh</button></div><div className="request-list">{requests.map((item) => <button className={`request-row selectable ${selected?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => void selectRequest(item)}><span className={`category ${item.category}`}>{item.category.replace("_", " ")}</span><div className="request-main"><strong>{item.content}</strong><small>{item.ticket?.id || item.id} / {item.status.replaceAll("_", " ")}</small></div><span className={`status ${item.status}`}>{item.status.replaceAll("_", " ")}</span></button>)}{!requests.length && <div className="empty">No visible requests yet.</div>}</div></div><RequestDetail item={selected} /></section></>}
    {tab === "approvals" && <section className="panel table-panel"><div className="panel-title"><div><span className="section-no">IT CONTROL ROOM / APPROVALS</span><h2>Protected actions</h2></div><span className="mode-pill orange">NO SILENT WRITES</span></div><div className="approval-list">{approvals.map((item) => <article className="approval-card" key={item.id}><div className="approval-summary"><span className="risk">{item.proposal.risk}</span><strong>{item.proposal.action_type.replaceAll("_", " ")}</strong><small>{item.proposal.request_id} / {item.status}</small></div><div className="proposal-payload"><b>Suggested action</b><p>{String(item.proposal.payload.ai_draft || item.proposal.payload.draft || item.proposal.payload.reason || "Protected action prepared for review.")}</p><code>{JSON.stringify(item.proposal.payload, null, 2)}</code></div>{item.status === "pending" ? <div className="approval-actions"><button className="reject" disabled={busy} onClick={() => void decide(item, "reject")}>Reject</button><button className="approve" disabled={busy} onClick={() => void decide(item, "approve")}>Approve and execute</button></div> : <div className="decision-note"><b>{item.status.toUpperCase()}</b><span>{item.decided_by || "System"}{item.note ? `: ${item.note}` : ""}</span></div>}</article>)}{!approvals.length && <div className="empty">No approvals have been created yet.</div>}</div></section>}<footer><span>DEMO DATA IS STORED IN SQLITE</span><span>PROPOSE. APPROVE. AUDIT.</span></footer></main>;
}

function Citations({ citations }: { citations: Citation[] }) { return citations.length ? <div className="citations">{citations.map((citation, index) => <div key={`${citation.title}-${index}`}><b>[{index + 1}] {citation.title}{citation.page ? ` / section ${citation.page}` : ""}</b><small>{citation.excerpt}</small></div>)}</div> : null; }
function RequestDetail({ item }: { item: RequestItem | null }) { if (!item) return <aside className="panel detail-panel"><span className="section-no">03 / REQUEST DETAIL</span><h2>Select a request</h2><p className="muted">The selected request shows its route, answer, evidence, proposed action, and outcome.</p></aside>; return <aside className="panel detail-panel"><span className="section-no">03 / REQUEST DETAIL</span><span className={`status ${item.status}`}>{item.status.replaceAll("_", " ")}</span><h2>{item.ticket?.id || item.id}</h2><p className="muted">Routed to {item.assigned_agent || "human review"}: {item.rationale}</p>{item.answer && <><b className="detail-label">AI RESPONSE</b><p className="detail-answer">{item.answer}</p><Citations citations={item.citations} /></>}{item.proposals?.map((proposal) => <div className="detail-proposal" key={proposal.id}><b className="detail-label">PROPOSED ACTION</b><strong>{proposal.action_type.replaceAll("_", " ")}</strong><p>{String(proposal.payload.ai_draft || proposal.payload.draft || proposal.payload.reason || "Protected action prepared for IT review.")}</p><small>{proposal.approval?.status === "approved" ? "Approved and executed in the simulator." : proposal.approval?.status === "rejected" ? "Rejected. No external change was made." : "Awaiting IT administrator approval."}</small></div>)}</aside>; }
