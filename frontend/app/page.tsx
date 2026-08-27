"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const demoHeaders = { "x-demo-user": "demo-admin", "x-workspace-id": "demo-workspace" };

type RequestItem = {
  id: string; content: string; source: string; status: string; category: string;
  severity: string; confidence: number; assigned_agent?: string; answer?: string;
  citations: Array<{ title: string; page?: number; section?: string; excerpt: string }>;
  ticket?: { id: string; status: string };
  proposals?: Array<{ id: string; action_type: string; status: string; approval?: { id: string; status: string } }>;
};
type Approval = { id: string; status: string; proposal: { id: string; request_id: string; action_type: string; risk: string; payload: Record<string, unknown> } };
type Call = { id: string; status: string; transcript: Array<{ speaker: string; text: string }>; request_id?: string };
type Slot = { slot_id: string; starts_at: string; available: boolean };

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...options, headers: { ...demoHeaders, ...(options.headers || {}) } });
  if (!response.ok) throw new Error(await response.text() || `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export default function Home() {
  const [tab, setTab] = useState<"inbox" | "ask" | "calls" | "approvals" | "health">("inbox");
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [health, setHealth] = useState<Array<{ name: string; kind: string; status: string; mode: string }>>([]);
  const [content, setContent] = useState("");
  const [answer, setAnswer] = useState<{ answer: string; grounded: boolean; confidence: number; citations: Array<{ title: string; page?: number; excerpt: string }> } | null>(null);
  const [question, setQuestion] = useState("");
  const [call, setCall] = useState<Call | null>(null);
  const [callMessage, setCallMessage] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const [nextRequests, nextApprovals, nextHealth] = await Promise.all([
        api<RequestItem[]>("/v1/requests"), api<Approval[]>("/v1/approvals"), api<typeof health>("/v1/integrations/health"),
      ]);
      setRequests(nextRequests); setApprovals(nextApprovals.filter((item) => item.status === "pending")); setHealth(nextHealth);
    } catch (err) { setError(err instanceof Error ? err.message : "API unavailable"); }
  }
  useEffect(() => { void refresh(); }, []);

  async function submitRequest() {
    if (!content.trim()) return;
    setBusy(true); setError("");
    try { await api("/v1/requests", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ content }) }); setContent(""); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not create request"); }
    finally { setBusy(false); }
  }

  async function askKnowledge() {
    if (!question.trim()) return;
    setBusy(true); setError("");
    try { setAnswer(await api<typeof answer>("/v1/knowledge/query", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Knowledge base unavailable"); }
    finally { setBusy(false); }
  }

  async function startCall() {
    try { setCall(await api<Call>("/v1/calls", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ caller_name: "Jordan Example", caller_email: "jordan@example.com", line_busy: true }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not start call"); }
  }
  async function sendCallMessage() {
    if (!call || !callMessage.trim()) return;
    try { setCall(await api<Call>(`/v1/calls/${call.id}/messages`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ content: callMessage }) })); setCallMessage(""); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not process call"); }
  }
  async function loadSlots() { try { setSlots(await api<Slot[]>("/v1/calendar/availability")); } catch (err) { setError(err instanceof Error ? err.message : "Calendar unavailable"); } }
  async function book(slot: Slot) {
    if (!call) return;
    try { await api(`/v1/calls/${call.id}/schedule`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ service_type: "Technician visit", slot_id: slot.slot_id }) }); await loadSlots(); }
    catch (err) { setError(err instanceof Error ? err.message : "Booking failed"); }
  }
  async function decide(id: string, decision: "approve" | "reject") {
    try { await api(`/v1/approvals/${id}/${decision}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ note: "Reviewed in service desk console" }) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Approval failed"); }
  }

  const stats = { total: requests.length, waiting: requests.filter((item) => item.status === "awaiting_approval").length, humans: requests.filter((item) => item.status === "awaiting_human").length, resolved: requests.filter((item) => item.status === "resolved").length };
  return <main className="shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">SD</span><div><strong>SERVICE DESK AI</strong><small>OPERATIONS CONTROL</small></div></div><div className="identity"><span className="live-dot" /> DEMO WORKSPACE <span className="identity-divider" /> Duc-Anh Nguyen / ADMIN</div></header>
    <section className="hero"><div><p className="eyebrow">GUARDED OPERATIONS COPILOT / V0.1</p><h1>Turn every request<br /><em>into a safe next step.</em></h1><p className="lede">One desk for supply chain exceptions, customer care, employee policy, and the calls that arrive when every line is busy.</p></div><div className="hero-orbit"><span>ERP</span><span>CRM</span><span>HRM</span><b>AI</b></div></section>
    <nav className="tabs">{(["inbox", "ask", "calls", "approvals", "health"] as const).map((item) => <button className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)}>{item === "ask" ? "Knowledge desk" : item === "health" ? "Integrations" : item[0].toUpperCase() + item.slice(1)}{item === "approvals" && stats.waiting > 0 && <i>{stats.waiting}</i>}</button>)}</nav>
    {error && <div className="error" role="alert">{error}</div>}
    {tab === "inbox" && <>
      <section className="metric-row"><Metric label="OPEN REQUESTS" value={stats.total} note="across all channels" /><Metric label="AWAITING APPROVAL" value={stats.waiting} note="protected mutations" accent="orange" /><Metric label="HUMAN REVIEW" value={stats.humans} note="low confidence or unsafe" accent="red" /><Metric label="RESOLVED" value={stats.resolved} note="closed by workflow" accent="green" /></section>
      <section className="content-grid"><div className="panel request-panel"><div className="panel-title"><div><span className="section-no">01 / INTAKE</span><h2>New request</h2></div><span className="mode-pill">ROUTER ONLINE</span></div><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="Describe a supply-chain, customer, employee, or scheduling request..." /><div className="composer-foot"><span>Input is validated, classified, and audited before any tool call.</span><button className="primary" disabled={busy} onClick={() => void submitRequest()}>{busy ? "Routing..." : "Create and triage"}<b>-&gt;</b></button></div><div className="demo-prompts"><button onClick={() => setContent("Inventory for gateway batteries is below the reorder point and the supplier PO is late.")}>ERP / late PO</button><button onClick={() => setContent("Customer reports that her room sensor stopped sending temperature readings.")}>CRM / sensor support</button><button onClick={() => setContent("I am an employee and need to know whether I can request three days of leave next month.")}>HR / leave policy</button></div></div><aside className="panel safety-panel"><span className="section-no">SAFETY LAYER</span><h2>Human control<br /><em>is part of the flow.</em></h2><div className="safety-line"><b>01</b><span>Typed tools only</span><small>Agents cannot invent integrations.</small></div><div className="safety-line"><b>02</b><span>Risk-based approval</span><small>ERP, CRM, HRM writes pause.</small></div><div className="safety-line"><b>03</b><span>Evidence or escalation</span><small>Unsupported answers abstain.</small></div></aside></section>
      <section className="panel table-panel"><div className="panel-title"><div><span className="section-no">02 / WORK QUEUE</span><h2>Requests and tickets</h2></div><button className="quiet" onClick={() => void refresh()}>Refresh</button></div><div className="request-list">{requests.map((item) => <article className="request-row" key={item.id}><span className={`category ${item.category}`}>{item.category.replace("_", " ")}</span><div className="request-main"><strong>{item.content}</strong><small>{item.id} / {item.assigned_agent || "Human review"}</small></div><span className={`status ${item.status}`}>{item.status.replaceAll("_", " ")}</span><span className="confidence">{Math.round(item.confidence * 100)}%</span></article>)}{!requests.length && <div className="empty">No requests yet. Use one of the demo prompts above.</div>}</div></section>
    </>}
    {tab === "ask" && <section className="split-page"><div className="panel ask-panel"><span className="section-no">KNOWLEDGE DESK / RAG</span><h2>Ask an approved procedure.</h2><p className="muted">Answers are grounded in the service-desk corpus and cannot perform mutations.</p><div className="ask-box"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="e.g. What should an operator check when a purchase order is late?" /><button className="primary" onClick={() => void askKnowledge()}>Search and answer -&gt;</button></div>{answer && <div className="answer"><div className="answer-head"><span className={answer.grounded ? "grounded" : "abstained"}>{answer.grounded ? "GROUNDED" : "ABSTAINED"}</span><span>{Math.round(answer.confidence * 100)}% confidence</span></div><p>{answer.answer}</p><div className="citations">{answer.citations.map((citation, index) => <div key={`${citation.title}-${index}`}><b>[{index + 1}] {citation.title}{citation.page ? ` / p.${citation.page}` : ""}</b><small>{citation.excerpt}</small></div>)}</div></div>}</div><aside className="panel corpus-panel"><span className="section-no">CORPUS</span><h2>5 approved playbooks</h2><p>Supply chain, CRM support, HR leave, appointments, and escalation policy.</p><div className="corpus-stamp">CITATIONS REQUIRED<br /><b>NO EVIDENCE / NO CLAIM</b></div></aside></section>}
    {tab === "calls" && <section className="split-page"><div className="panel call-panel"><span className="section-no">VOICE SIMULATOR / BUSY LINE</span><h2>Answer the call.<br /><em>Capture the need.</em></h2>{!call ? <button className="primary" onClick={() => void startCall()}>Start simulated call -&gt;</button> : <><div className="transcript">{call.transcript.map((line, index) => <div className={line.speaker} key={index}><span>{line.speaker === "assistant" ? "AI" : "CALLER"}</span><p>{line.text}</p></div>)}</div><div className="call-compose"><input value={callMessage} onChange={(event) => setCallMessage(event.target.value)} placeholder="Type caller response..." onKeyDown={(event) => { if (event.key === "Enter") void sendCallMessage(); }} /><button onClick={() => void sendCallMessage()}>Send</button></div><div className="schedule"><div><strong>Need a technician?</strong><small>Check availability and confirm a slot.</small></div><button className="quiet" onClick={() => void loadSlots()}>Check calendar</button>{slots.map((slot) => slot.available && <button className="slot" key={slot.slot_id} onClick={() => void book(slot)}>{new Date(slot.starts_at).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}</button>)}</div></>}</div><aside className="panel call-policy"><span className="section-no">CALL POLICY</span><div className="big-number">24/7</div><p>When all service lines are busy, the assistant takes a structured request and confirms every booking.</p><hr /><p>Unclear, abusive, unauthenticated, and protected requests go to a human queue.</p></aside></section>}
    {tab === "approvals" && <section className="panel table-panel"><div className="panel-title"><div><span className="section-no">CONTROL ROOM / APPROVALS</span><h2>Protected actions</h2></div><span className="mode-pill orange">NO SILENT WRITES</span></div><div className="approval-list">{approvals.map((item) => <article className="approval-row" key={item.id}><div><span className="risk">{item.proposal.risk}</span><strong>{item.proposal.action_type.replaceAll("_", " ")}</strong><small>{item.proposal.request_id} / proposal {item.proposal.id}</small></div><div className="approval-actions"><button className="reject" onClick={() => void decide(item.id, "reject")}>Reject</button><button className="approve" onClick={() => void decide(item.id, "approve")}>Approve action</button></div></article>)}{!approvals.length && <div className="empty">No pending approvals. Submit an ERP, CRM, or HR demo request.</div>}</div></section>}
    {tab === "health" && <section className="panel table-panel"><div className="panel-title"><div><span className="section-no">SYSTEMS / ADAPTER HEALTH</span><h2>Integration boundary</h2></div><span className="mode-pill">SIMULATORS ACTIVE</span></div><div className="health-grid">{health.map((item) => <div className="health-card" key={item.name}><span className="health-dot" /><strong>{item.name}</strong><small>{item.kind || item.mode} / {item.mode}</small><b>{item.status}</b></div>)}</div></section>}
    <footer><span>SERVICE DESK AI / SYNTHETIC OPERATIONS DATA</span><span>PROPOSE. APPROVE. AUDIT.</span></footer>
  </main>;
}

function Metric({ label, value, note, accent = "cyan" }: { label: string; value: number; note: string; accent?: string }) { return <article className={`metric ${accent}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>; }
