import { useEffect, useState } from "react";
import { Evidence } from "./Evidence";
import { Icon } from "./Icon";
import type { Capabilities, History, Report, Scan, Scenario } from "./types";

const pages = ["Scanner", "Attack lab", "Evaluation", "History", "System"] as const;
type Page = (typeof pages)[number];
const sources = ["user", "retrieved_document", "webpage", "email", "attachment", "tool_response", "agent"];

function Badge({ value }: { value: string }) {
  return <span className={`badge badge-${value.toLowerCase().replaceAll("_", "-")}`}>{value.replaceAll("_", " ")}</span>;
}
function number(value: number | undefined, digits = 1) {
  return value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export default function App() {
  const [page, setPage] = useState<Page>("Scanner");
  const [credential, setCredential] = useState("");
  const [content, setContent] = useState("");
  const [scannedContent, setScannedContent] = useState("");
  const [source, setSource] = useState("retrieved_document");
  const [scan, setScan] = useState<Scan | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [cases, setCases] = useState<Scenario[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<History[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(credential ? { Authorization: `Bearer ${credential}` } : {}) },
    });
    if (!response.ok) {
      if (response.status === 401) throw new Error("Authentication required. Enter the API credential and reconnect.");
      if (response.status === 429) throw new Error("Rate limit reached. Try again shortly.");
      if (response.status === 404) throw new Error("This feature is unavailable in the current deployment.");
      throw new Error(`Request failed (${response.status}). Review the input and service status.`);
    }
    return response.json() as Promise<T>;
  }

  async function perform(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try { await work(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Request failed."); }
    finally { setBusy(false); }
  }

  async function load(selected: Page) {
    setPage(selected);
    await perform(async () => {
      if (selected === "Attack lab") setCases(await request<Scenario[]>("/v2/lab"));
      if (selected === "Evaluation") setReport(await request<Report>("/v2/evaluation"));
      if (selected === "History") setHistory(await request<History[]>("/v2/history"));
      if (selected === "System") setCapabilities(await request<Capabilities>("/v2/system/capabilities"));
    });
  }

  useEffect(() => {
    void perform(async () => setCapabilities(await request<Capabilities>("/v2/system/capabilities")));
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await perform(async () => {
      const result = await request<Scan>("/v2/scan", { method: "POST", body: JSON.stringify({ text: content, source }) });
      setScan(result);
      setScannedContent(content);
      setCapabilities(await request<Capabilities>("/v2/system/capabilities"));
    });
  }

  async function clearHistory() {
    await perform(async () => {
      await request<{ cleared: boolean }>("/v2/history", { method: "DELETE" });
      setHistory([]);
    });
  }

  return <div className="shell">
    <aside className="sidebar">
      <a href="#main" className="brand" aria-label="kjnlae home">
        <img src="/assets/logo.svg" width="38" height="38" alt="" />
        <span>kjnlae<small>SECURITY GATEWAY</small></span>
      </a>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Primary navigation">
        {pages.map((item, index) => <button key={item} type="button" className={page === item ? "nav-active" : ""}
          aria-current={page === item ? "page" : undefined} onClick={() => void load(item)}>
          <Icon name={(["scan", "lab", "chart", "history", "settings"] as const)[index]} />{item}
        </button>)}
      </nav>
      <div className="sidebar-footer">
        <div className="connection"><span className={capabilities ? "signal signal-on" : "signal"} />{capabilities ? "API connected" : "API unavailable"}</div>
        <label htmlFor="credential">API CREDENTIAL <span>session only</span></label>
        <input id="credential" type="password" autoComplete="off" value={credential}
          onChange={event => setCredential(event.target.value)} />
        <button type="button" className="reconnect" onClick={() => void load("System")}>Reconnect</button>
      </div>
    </aside>
    <main id="main" className="main">
      <header className="topbar"><span>Workspace <span className="crumb">/ {page}</span></span>
        <span className="top-status"><span className={capabilities?.model_status === "AVAILABLE" ? "signal signal-on" : "signal signal-warn"} />
          Model {capabilities?.model_status?.toLowerCase() ?? "unknown"}</span></header>
      <div className="content">
        <div className="page-intro"><div><div className="eyebrow">KJNLAE / {page.toUpperCase()}</div><h1>{page}</h1>
          <p>{page === "Scanner" ? "Inspect untrusted content with the verified local model." :
            page === "Attack lab" ? "Scripted attacks and the action boundary they reach." :
            page === "Evaluation" ? "Measured fixture results, with coverage and provenance." :
            page === "History" ? "Local metadata only. Submitted text is not stored." :
            "Configured detection and independent security controls."}</p></div>
          <span className="policy-chip">{capabilities?.policy ?? "MODEL REQUIRED"}</span></div>
        {error && <div className="alert" role="alert">{error}</div>}

        {page === "Scanner" && <>
          <div className="stat-grid">
            <div className="stat"><span>DETECTION PIPELINE</span><strong>Fine-tuned NLP</strong><small>Single model, no fallback</small></div>
            <div className="stat"><span>MODEL STATUS</span><strong>{capabilities?.model_status ?? "Unknown"}</strong><small>Verified local artifact</small></div>
            <div className="stat"><span>LAST DECISION</span><strong>{scan?.policy_decision ?? "—"}</strong><small>{scan?.detection_status?.replaceAll("_", " ") ?? "No scan yet"}</small></div>
            <div className="stat"><span>COVERAGE</span><strong>{scan ? scan.inspection_complete ? "Complete" : "Incomplete" : "—"}</strong><small>{scan ? `${scan.coverage.windows} model window(s)` : "Awaiting input"}</small></div>
          </div>
          <div className="two-column">
            <section className="panel"><div className="panel-heading"><div><div className="eyebrow">01 / INPUT</div><h2>Inspect content</h2></div><span>32,768 character limit</span></div>
              <form onSubmit={event => void submit(event)}>
                <label htmlFor="source">Source type</label>
                <select id="source" value={source} onChange={event => setSource(event.target.value)}>{sources.map(item => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select>
                <label htmlFor="content">Untrusted content</label>
                <textarea id="content" value={content} maxLength={32768} onChange={event => setContent(event.target.value)}
                  placeholder="Paste a user message, retrieved passage, tool response, or email..." rows={13} required />
                <div className="form-footer"><span>{content.length.toLocaleString()} / 32,768 characters</span>
                  <button type="submit" className="primary" disabled={busy || !content.trim()}>{busy ? "Inspecting…" : "Run inspection"}</button></div>
              </form></section>
            <section className="panel result-panel"><div className="panel-heading"><div><div className="eyebrow">02 / RESULT</div><h2>Decision evidence</h2></div>{scan && <Badge value={scan.policy_decision} />}</div>
              {!scan ? <div className="empty-state"><Icon name="shield" /><strong>No result yet</strong><p>Submit content to see the model decision and coverage.</p></div> : <>
                <div className="result-status"><Badge value={scan.detection_status} /><span>{scan.latency_ms.toFixed(1)} ms</span></div>
                <p className="result-copy">{scan.explanation}</p>
                <div className="detail-grid"><div><span>MODEL SCORE</span><strong>{scan.model_score === null ? "Unavailable" : number(scan.model_score)}</strong></div>
                  <div><span>INSPECTED VIEWS</span><strong>{scan.coverage.views}</strong></div><div><span>MODEL WINDOWS</span><strong>{scan.coverage.windows}</strong></div>
                  <div><span>RISK LEVEL</span><strong>{scan.risk_level}</strong></div></div>
                <div className="mitigation"><strong>Recommended action</strong><p>{scan.recommended_action}</p></div>
              </>}</section>
          </div>
          {scan && <section className="panel evidence-panel"><div className="panel-heading"><div><div className="eyebrow">03 / SOURCE</div><h2>Evidence in original content</h2></div><span>{scan.evidence.length} model window(s) above threshold</span></div>
            <Evidence text={scannedContent} spans={scan.evidence.map(({start, end}) => ({start, end}))} />
            <p className="footnote">Highlights identify model windows; they do not isolate the exact malicious phrase. Model scores are not calibrated attack probabilities.</p></section>}
        </>}

        {page === "Attack lab" && <section className="panel"><div className="panel-heading"><div><div className="eyebrow">SYNTHETIC SANDBOX</div><h2>Boundary outcomes</h2></div><span>{cases.length} scenarios</span></div>
          <p className="panel-description">Scripted proposals, synthetic data, and local callbacks. No live LLM or external destination is used.</p>
          {cases.length === 0 ? <div className="empty-state">{busy ? "Running scenarios…" : "No scenarios available."}</div> :
            <div className="case-list">{cases.map(item => <article className="case" key={item.id}>
              <div className="case-top"><div><span className="eyebrow">{item.id}</span><h3>{item.task}</h3></div><Badge value={item.action_decision} /></div>
              <div className="case-content"><div><span>UNTRUSTED INPUT</span><p>{item.input}</p></div><div><span>MODEL DECISION</span><strong>{item.detection_decision}</strong><small>{item.detection_status}</small></div><div><span>ACTION OUTCOME</span><strong>{item.action_decision}</strong><small>{item.action_reason}</small></div></div>
            </article>)}</div>}</section>}

        {page === "Evaluation" && <>{report ? <><div className="stat-grid">
          <div className="stat"><span>FIXTURE CASES</span><strong>{report.dataset.count}</strong><small>{report.dataset.attack_count} labeled attacks</small></div>
          <div className="stat"><span>MODEL COVERAGE</span><strong>{number(report.detector.coverage)}</strong><small>{report.detector.complete_count} / {report.detector.count} complete</small></div>
          <div className="stat"><span>F1 SCORE</span><strong>{number(report.detector.f1)}</strong><small>{report.detector.status}</small></div>
          <div className="stat"><span>ACTION PREVENTION</span><strong>{number(report.defense.unauthorized_action_prevention_rate)}</strong><small>Scripted sandbox only</small></div>
          </div><div className="two-column"><section className="panel"><div className="panel-heading"><div><div className="eyebrow">DETECTION</div><h2>Fixture performance</h2></div><Badge value={report.detector.status} /></div>
            {report.detector.status === "MEASURED" && report.detector.confusion_matrix ? <><div className="metric-row"><span>Precision <b>{number(report.detector.precision)}</b></span><span>Recall <b>{number(report.detector.recall)}</b></span><span>False positive rate <b>{number(report.detector.false_positive_rate)}</b></span></div>
              <div className="matrix" aria-label="Confusion matrix"><div>TRUE POSITIVE<strong>{report.detector.confusion_matrix.tp}</strong></div><div>FALSE POSITIVE<strong>{report.detector.confusion_matrix.fp}</strong></div><div>FALSE NEGATIVE<strong>{report.detector.confusion_matrix.fn}</strong></div><div>TRUE NEGATIVE<strong>{report.detector.confusion_matrix.tn}</strong></div></div></> : <p className="alert inline">Accuracy metrics withheld: model inspection was incomplete.</p>}</section>
            <section className="panel"><div className="panel-heading"><div><div className="eyebrow">DEFENSE</div><h2>Observed action outcomes</h2></div></div><div className="metric-list"><div><span>Attack success rate</span><strong>{number(report.defense.attack_success_rate)}</strong></div><div><span>Authorized completion</span><strong>{number(report.defense.authorized_task_completion_rate)}</strong></div><div><span>Benign task rejection</span><strong>{number(report.defense.benign_task_rejection_rate)}</strong></div></div><p className="footnote">{report.defense.simulation}</p></section></div>
          <section className="panel"><div className="panel-heading"><div><div className="eyebrow">PROVENANCE</div><h2>Dataset details</h2></div></div><dl className="provenance"><div><dt>Name</dt><dd>{report.dataset.name}</dd></div><div><dt>SHA256</dt><dd className="mono">{report.dataset.sha256}</dd></div><div><dt>Scope</dt><dd>{report.dataset.limitations}</dd></div></dl></section></> : <div className="empty-state">{busy ? "Measuring fixture suite…" : "Evaluation unavailable."}</div>}</>}

        {page === "History" && <section className="panel"><div className="panel-heading"><div><div className="eyebrow">LOCAL AUDIT</div><h2>Recent inspections</h2></div><button type="button" onClick={() => void clearHistory()} disabled={busy || history.length === 0}>Clear history</button></div>
          {history.length === 0 ? <div className="empty-state">No local inspection metadata.</div> : <div className="table-scroll"><table><thead><tr><th>Time</th><th>Decision</th><th>Detection</th><th>Model</th><th>Latency</th></tr></thead><tbody>{history.map(item => <tr key={item.id}><td>{new Date(item.at * 1000).toLocaleString()}</td><td><Badge value={item.policy_decision} /></td><td>{item.detection_status}</td><td>{item.model_status}</td><td>{item.latency_ms.toFixed(1)} ms</td></tr>)}</tbody></table></div>}</section>}

        {page === "System" && <div className="two-column"><section className="panel"><div className="panel-heading"><div><div className="eyebrow">RUNTIME</div><h2>Detection service</h2></div></div>
          <div className="metric-list"><div><span>Model status</span><Badge value={capabilities?.model_status ?? "UNKNOWN"} /></div><div><span>Detector</span><strong>{capabilities?.detector ?? "Unavailable"}</strong></div><div><span>Threshold</span><strong>{capabilities?.threshold ?? "—"}</strong></div><div><span>Policy</span><strong>{capabilities?.policy ?? "—"}</strong></div><div><span>Version</span><strong>{capabilities?.version ?? "—"}</strong></div></div>
          {capabilities?.model_config_error && <p className="alert inline">Artifact configuration error: {capabilities.model_config_error}</p>}</section>
          <section className="panel"><div className="panel-heading"><div><div className="eyebrow">BOUNDARIES</div><h2>Security controls</h2></div></div><div className="metric-list"><div><span>Action authorization</span><strong>{capabilities?.action_policy ?? "—"}</strong></div><div><span>Output inspection</span><strong>{capabilities?.output_policy ?? "—"}</strong></div><div><span>Environment</span><strong>{capabilities?.production ? "Production" : "Local development"}</strong></div></div><ul className="limitations">{capabilities?.limitations.map(item => <li key={item}>{item}</li>)}</ul></section></div>}
      </div>
    </main>
  </div>;
}
