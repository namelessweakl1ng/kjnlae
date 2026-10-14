import { useEffect, useState, type FormEvent } from "react";
import { Evidence } from "./Evidence";
import { WindowScores } from "./WindowScores";
import type { Capabilities, Scan } from "./types";

const sources = ["user", "retrieved_document", "webpage", "email", "attachment", "tool_response", "agent"];

export function withinInputLimit(text: string) {
  return Array.from(text).length <= 32768;
}

function formatPercent(value: number | null | undefined) {
  return value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}

function Status({ value }: { value: string }) {
  return <span className={`status status-${value.toLowerCase().replaceAll("_", "-")}`}>{value.replaceAll("_", " ")}</span>;
}

export default function App() {
  const [credential, setCredential] = useState("");
  const [content, setContent] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [source, setSource] = useState("retrieved_document");
  const [scan, setScan] = useState<Scan | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [selectedWindow, setSelectedWindow] = useState<number | null>(null);

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(credential ? { Authorization: `Bearer ${credential}` } : {}) },
    });
    if (!response.ok) {
      if (response.status === 401) throw new Error("Authentication required. Enter the API credential and reconnect.");
      if (response.status === 429) throw new Error("Rate limit reached. Try again shortly.");
      throw new Error(`Request failed (${response.status}). Check the input and server status.`);
    }
    return response.json() as Promise<T>;
  }

  async function refresh() {
    setChecking(true);
    setError("");
    try { setCapabilities(await request<Capabilities>("/v2/system/capabilities")); }
    catch (cause) { setCapabilities(null); setError(cause instanceof Error ? cause.message : "Connection failed."); }
    finally { setChecking(false); }
  }

  useEffect(() => { void refresh(); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setScan(null);
    setSelectedWindow(null);
    try {
      const response = await request<Scan>("/v2/scan", { method: "POST", body: JSON.stringify({ text: content, source }) });
      setScan(response);
      setSubmitted(content);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Inspection failed."); }
    finally { setBusy(false); }
  }

  const highlighted = selectedWindow === null ? scan?.evidence ?? [] : [scan?.windows[selectedWindow]].filter((x) => x != null);
  const ready = capabilities?.model_status === "AVAILABLE";

  return <div className="app-shell">
    <aside className="rail">
      <a className="brand" href="#main" aria-label="kjnlae scanner">
        <img src="/assets/logo.svg" width="38" height="38" alt="" />
        <span>kjnlae<small>MODEL INSPECTION</small></span>
      </a>
      <div className="rail-section"><span className="rail-label">WORKSPACE</span><strong className="rail-active">Scanner</strong></div>
      <div className="rail-bottom">
        <span className="rail-label">LOCAL SERVICE</span>
        <div className="connection"><span className={`dot ${ready ? "on" : ""}`} />{checking ? "Connecting…" : capabilities ? `Model ${capabilities.model_status.toLowerCase()}` : "API unavailable"}</div>
        <label htmlFor="credential">API credential <small>kept in this page only</small></label>
        <input id="credential" type="password" autoComplete="off" value={credential} onChange={event => setCredential(event.target.value)} />
        <button type="button" className="secondary dark" onClick={() => void refresh()} disabled={checking}>Reconnect</button>
      </div>
    </aside>
    <main id="main" className="main">
      <header className="topbar"><span>SECURITY / SCANNER</span><span className="top-model"><span className={`dot ${ready ? "on" : ""}`} />{checking ? "Checking model" : capabilities?.model_status ?? "Unknown"}</span></header>
      <div className="workspace">
        <div className="intro"><div><span className="eyebrow">LOCAL MODEL · NO REMOTE INFERENCE</span><h1>Inspect untrusted content</h1><p>See the model’s prediction, the policy decision, and every text window it scored.</p></div></div>
        {error && <div className="notice error" role="alert">{error}</div>}
        {!checking && capabilities && !ready && <div className="notice" role="status">Model {capabilities.model_status.toLowerCase()}. Install the verified artifact with <code>kjnlae model download</code>, then run <code>kjnlae doctor</code>. Scans cannot be cleared while inference is unavailable.</div>}
        <div className="workspace-grid">
          <section className="card input-card" aria-labelledby="input-heading">
            <div className="card-head"><div><span className="eyebrow">01 / INPUT</span><h2 id="input-heading">Content to inspect</h2></div><span className="fine">32,768 characters max</span></div>
            <form onSubmit={event => void submit(event)}>
              <label htmlFor="source">Source</label>
              <select id="source" value={source} onChange={event => setSource(event.target.value)}>{sources.map(item => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select>
              <label htmlFor="content">Untrusted content</label>
              <textarea id="content" value={content} onChange={event => {
                if (withinInputLimit(event.target.value)) setContent(event.target.value);
                else setError("Input exceeds 32,768 characters.");
              }} maxLength={65536} rows={13} required placeholder="Paste a message, retrieved passage, email, or tool response…" />
              <div className="form-actions"><span>{Array.from(content).length.toLocaleString()} / 32,768</span><button className="primary" type="submit" disabled={busy || !content.trim()}>{busy ? "Inspecting…" : "Run inspection"}</button></div>
            </form>
          </section>
          <section className="card result-card" aria-labelledby="result-heading">
            <div className="card-head"><div><span className="eyebrow">02 / RESULT</span><h2 id="result-heading">Model prediction</h2></div>{scan && <Status value={scan.policy_decision} />}</div>
            {busy ? <div className="empty" role="status"><span className="activity" />Running local inference. The result appears when the inspection and policy decision finish.</div> : !scan ? <div className="empty">Submit content to see a measured score and inspection coverage.</div> : <div className="result-body">
              <div className="result-status"><Status value={scan.detection_status} /><span>{scan.model_status} · {scan.latency_ms.toFixed(1)} ms</span></div>
              <div className="hero-score"><span>INJECTION-CLASS SCORE</span><strong>{formatPercent(scan.model_score)}</strong><div className="score-track" aria-label={`Model score ${formatPercent(scan.model_score)}; threshold ${formatPercent(scan.threshold)}`}>
                {scan.model_score != null && <span className="score-fill" style={{ width: `${scan.model_score * 100}%` }} />}
                {scan.threshold != null && <span className="threshold-line" style={{ left: `${scan.threshold * 100}%` }} />}
              </div><small>Decision threshold {formatPercent(scan.threshold)} · model softmax score, not an attack probability</small></div>
              <dl className="facts"><div><dt>Inspection</dt><dd>{scan.inspection_complete ? "Complete" : "Incomplete"}</dd></div><div><dt>Model windows</dt><dd>{scan.coverage.windows}</dd></div><div><dt>Views inspected</dt><dd>{scan.coverage.views}</dd></div><div><dt>Model identity</dt><dd className="mono">{scan.model_hash?.slice(0, 12) ?? "Unavailable"}</dd></div></dl>
              <p className="result-copy">{scan.explanation}</p><div className="guidance"><strong>Recommended action</strong><p>{scan.recommended_action}</p></div>
            </div>}
          </section>
        </div>
        {scan && <div className="inspection-grid">
          <section className="card" aria-labelledby="windows-heading"><div className="card-head"><div><span className="eyebrow">03 / MEASUREMENTS</span><h2 id="windows-heading">Inspected windows</h2></div><span className="fine">{scan.windows.length} scored</span></div>
            {scan.windows.length && scan.threshold != null ? <WindowScores windows={scan.windows} threshold={scan.threshold} text={submitted} selected={selectedWindow ?? -1} onSelect={setSelectedWindow} /> : <p className="card-note">No complete model-window scores are available for this inspection.</p>}
          </section>
          <section className="card" aria-labelledby="evidence-heading"><div className="card-head"><div><span className="eyebrow">04 / SOURCE</span><h2 id="evidence-heading">Original content</h2></div><span className="fine">{selectedWindow === null ? "Above-threshold windows" : `Window ${selectedWindow + 1}`}</span></div>
            <Evidence text={submitted} spans={highlighted.map(({ start, end }) => ({ start, end }))} />
            <p className="card-note">Highlights map scored windows to the submitted text. They do not identify a causal phrase. Transformed views may map to a broader source span.</p>
          </section>
        </div>}
        <footer>kjnlae is experimental. A scan is evidence for a decision; tool and data access still require independent authorization.</footer>
      </div>
    </main>
  </div>;
}
