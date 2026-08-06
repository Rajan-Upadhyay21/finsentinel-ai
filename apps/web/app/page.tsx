import { Activity, BrainCircuit, ShieldCheck, TriangleAlert, Workflow } from "lucide-react";

const metrics = [
  { label: "Transactions analyzed", value: "128,420", delta: "+12.8%" },
  { label: "Open investigations", value: "37", delta: "6 critical" },
  { label: "Agent success rate", value: "98.7%", delta: "+0.4%" },
  { label: "Median decision time", value: "4.8s", delta: "-1.2s" },
];

const agents = [
  ["Supervisor", "Planning investigation", "active"],
  ["Fraud Agent", "Scoring transaction", "active"],
  ["Behavior Agent", "Comparing customer baseline", "active"],
  ["Graph Agent", "Querying entity network", "queued"],
  ["Policy Agent", "Retrieving FRD-001", "complete"],
  ["Critic Agent", "Waiting for evidence", "queued"],
];

export default function Home() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><ShieldCheck size={24} /> FinSentinel</div>
        <nav>
          <a className="selected" href="#"><Activity size={18} /> Operations</a>
          <a href="#"><TriangleAlert size={18} /> Investigations</a>
          <a href="#"><Workflow size={18} /> Agent workflows</a>
          <a href="#"><BrainCircuit size={18} /> Model governance</a>
        </nav>
        <div className="security-badge">Security controls: healthy</div>
      </aside>

      <section className="content">
        <header>
          <div>
            <p className="eyebrow">BANKING AI OPERATIONS CENTER</p>
            <h1>Risk intelligence, continuously coordinated.</h1>
            <p className="muted">Live synthetic banking environment · Evidence-gated decisions · Human approval enabled</p>
          </div>
          <button>Start simulation</button>
        </header>

        <div className="metrics">
          {metrics.map((metric) => (
            <article className="metric" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.delta}</small>
            </article>
          ))}
        </div>

        <div className="grid">
          <article className="panel live-panel">
            <div className="panel-title"><h2>Live agent execution</h2><span className="live-dot">LIVE</span></div>
            <div className="workflow-line">
              {agents.map(([name, task, status], index) => (
                <div className={`agent ${status}`} key={name}>
                  <div className="agent-index">{index + 1}</div>
                  <div><strong>{name}</strong><p>{task}</p></div>
                  <span>{status}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="panel">
            <div className="panel-title"><h2>Current case</h2><span>#FRAUD-10421</span></div>
            <div className="risk-score"><strong>87</strong><span>/100</span></div>
            <p className="risk-label">High-risk investigation</p>
            <div className="evidence">
              <p><b>New device</b><span>+21 risk</span></p>
              <p><b>Behavioral outlier</b><span>+18 risk</span></p>
              <p><b>Risky merchant link</b><span>+16 risk</span></p>
              <p><b>Policy FRD-001</b><span>Review</span></p>
            </div>
            <button className="review">Open human review</button>
          </article>
        </div>

        <article className="panel table-panel">
          <div className="panel-title"><h2>Recent decisions</h2><span>Audit trail enabled</span></div>
          <table>
            <thead><tr><th>Case</th><th>Workflow</th><th>Risk</th><th>Decision</th><th>Confidence</th></tr></thead>
            <tbody>
              <tr><td>FRAUD-10421</td><td>Card fraud</td><td><b>Critical</b></td><td>Manual review</td><td>91%</td></tr>
              <tr><td>AML-08317</td><td>Structuring</td><td>High</td><td>Escalated</td><td>88%</td></tr>
              <tr><td>CRD-04102</td><td>Credit risk</td><td>Medium</td><td>Monitor</td><td>84%</td></tr>
            </tbody>
          </table>
        </article>
      </section>
    </main>
  );
}
