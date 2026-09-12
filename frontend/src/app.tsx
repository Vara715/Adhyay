import React, { useEffect, useState } from "react";
import "./styles.css";

interface Scenario {
  key: string;
  name: string;
  description: string;
}

interface CustomerCase {
  case_id: string;
  issue: string;
  impact: string;
  affected_service: string;
  status: string;
}

interface EvidenceItem {
  source: string;
  fact: string;
  kind?: "fact" | "hypothesis" | "verified";
}

interface VerificationOutcome {
  status: "verified" | "failed" | "inconclusive";
  detail: string;
  before: Record<string, any>;
  after: Record<string, any>;
}

interface ActionProposal {
  action_id: string;
  action: string;
  arguments: Record<string, any>;
  reason: string;
  evidence: string[];
  estimated_impact: Record<string, any>;
  risk: string;
  permission_level: "read_only" | "low_risk" | "high_risk";
  approval_status: string;
  outcome_summary?: string;
  verification?: VerificationOutcome;
}

interface AgentEvent {
  sequence?: number;
  event_id?: string;
  event_type: string;
  summary: string;
  created_at?: string;
  timestamp?: string;
  tool_name?: string;
}

interface FinalResult {
  conclusion: string;
  confidence: "low" | "medium" | "high";
  unresolved_issues: string[];
  actions_executed: string[];
}

interface AgentState {
  run_id: string;
  original_goal: string;
  customer_case?: CustomerCase;
  current_objective: string;
  current_hypothesis: string;
  evidence: EvidenceItem[];
  failures: string[];
  actions: string[];
  action_proposals: ActionProposal[];
  pending_action: ActionProposal | null;
  verification_notes: string[];
  events: AgentEvent[];
  status: "running" | "awaiting_approval" | "completed" | "failed" | "timed_out" | "step_limit_reached";
  final_result: FinalResult | null;
  step_count: number;
}

const API_BASE = "http://127.0.0.1:8000/api";

const DEFAULT_GOALS: Record<string, string> = {
  inventory_supplier_failure: "Revenue dropped significantly today. Investigate why and resolve it if possible.",
  payment_failure: "Payment gateway timeouts are reported. Investigate and restore transaction health.",
  deployment_service_failure: "Checkout error rate spiked after release DEP-502. Investigate why and fix it if possible.",
  misleading_initial_hypothesis: "Investigate checkout cart abandonment and pricing anomalies.",
};

function formatTimestamp(tsString?: string): string {
  if (!tsString) return "—";
  const d = new Date(tsString);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-US", { hour12: false });
}

export default function App() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("deployment_service_failure");
  const [goal, setGoal] = useState<string>(DEFAULT_GOALS["deployment_service_failure"]);
  const [threshold, setThreshold] = useState<string>("50000");
  const [currentRun, setCurrentRun] = useState<AgentState | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [systemHealth, setSystemHealth] = useState<{ status: string; llm_configured: boolean } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load health and scenarios
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then((data) => setSystemHealth(data))
      .catch(() => setSystemHealth({ status: "offline", llm_configured: false }));

    fetch(`${API_BASE}/scenarios`)
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setScenarios(data);
        }
      })
      .catch(() => {
        setScenarios([
          { key: "deployment_service_failure", name: "Deployment Service Failure", description: "Elevated error rate after checkout release DEP-502." },
          { key: "inventory_supplier_failure", name: "Inventory & Supplier Failure", description: "Delayed supplier shipment causes stockout." },
          { key: "payment_failure", name: "Payment Failure", description: "Gateway timeout surge." },
          { key: "misleading_initial_hypothesis", name: "Misleading Initial Hypothesis", description: "Pricing configuration discrepancy." },
        ]);
      });
  }, []);

  const handleScenarioChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const key = e.target.value;
    setSelectedScenario(key);
    if (DEFAULT_GOALS[key]) {
      setGoal(DEFAULT_GOALS[key]);
    }
  };

  // Poll for run state updates every 500ms when status is "running"
  useEffect(() => {
    if (!currentRun || currentRun.status !== "running") return;
    const interval = setInterval(() => {
      fetch(`${API_BASE}/runs/${currentRun.run_id}`)
        .then((res) => {
          if (!res.ok) throw new Error("Fetch run failed");
          return res.json();
        })
        .then((updated) => setCurrentRun(updated))
        .catch((err) => console.error("Poll error:", err));
    }, 500);
    return () => clearInterval(interval);
  }, [currentRun]);

  const startInvestigation = async () => {
    if (!goal.trim()) {
      setErrorMsg("Provide a non-empty operational investigation goal.");
      return;
    }
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: goal.trim(),
          scenario: selectedScenario,
          approval_threshold_inr: threshold,
          step_delay_seconds: 0.6, // Step pacing for live demonstration
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to start investigation");
      }
      const data: AgentState = await res.json();
      setCurrentRun(data);
    } catch (err: any) {
      if (err?.message === "Failed to fetch" || err?.name === "TypeError") {
        setErrorMsg("Backend server is offline. Please start it with: python -m uvicorn backend.main:app --reload");
      } else {
        setErrorMsg(err.message || "An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

  const submitApproval = async (approved: boolean) => {
    if (!currentRun) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/runs/${currentRun.run_id}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved, step_delay_seconds: 0.6 }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Approval decision failed");
      }
      const updated: AgentState = await res.json();
      setCurrentRun(updated);
    } catch (err: any) {
      if (err?.message === "Failed to fetch" || err?.name === "TypeError") {
        setErrorMsg("Backend server is offline. Please start it with: python -m uvicorn backend.main:app --reload");
      } else {
        setErrorMsg(err.message || "An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

  // Helper status label
  const getStatusLabel = () => {
    if (!currentRun) return "READY";
    if (currentRun.status === "awaiting_approval") return "WAITING FOR HUMAN APPROVAL";
    if (currentRun.status === "completed") return "RESOLVED";
    if (currentRun.status === "failed") return "FAILED / UNRESOLVED";
    if (currentRun.status === "step_limit_reached") return "MAX STEPS REACHED";
    if (currentRun.events.some((e) => e.event_type === "verification")) return "VERIFYING STATE";
    if (currentRun.events.some((e) => e.event_type === "adaptation")) return "ADAPTING TO OUTAGE";
    return "INVESTIGATING";
  };

  // Find latest proposal with verification outcome
  const verifiedProposal = currentRun?.action_proposals.find((p) => p.verification != null);

  return (
    <div className="app-shell">
      {/* Enterprise Header Bar */}
      <header className="app-header-bar">
        <div className="header-brand">
          <span className="logo-badge">A</span>
          <div className="header-title-group">
            <h1 className="header-app-name">Adhyay</h1>
            <span className="header-app-sub">AUTONOMOUS CUSTOMER & OPERATIONS RESOLUTION AGENT</span>
          </div>
        </div>
        <div className="header-status-group">
          <div className="status-pill">
            <span className="status-dot" style={{ backgroundColor: systemHealth?.status === "ok" ? "#22c55e" : "#f59e0b" }} />
            <span>System {systemHealth?.status === "ok" ? "Ready" : "Initializing"}</span>
          </div>
          <span style={{ opacity: 0.4 }}>|</span>
          <span>Environment: Demo</span>
        </div>
      </header>

      {/* Main Operational Container */}
      <main className="main-container">
        {/* Investigation Control Panel */}
        <section className="enterprise-panel">
          <div className="panel-header">
            <span>INVESTIGATION CONTROL</span>
            <span className="panel-header-sub">Operational Anomaly Resolution Entry</span>
          </div>
          <div className="panel-body">
            <div className="control-grid">
              <div className="form-group">
                <label className="form-label">Investigation Goal</label>
                <input
                  type="text"
                  className="form-input"
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  placeholder="Enter operational investigation goal..."
                />
              </div>
              <div className="form-group">
                <label className="form-label">Simulation Scenario</label>
                <select className="form-select" value={selectedScenario} onChange={handleScenarioChange}>
                  {scenarios.map((sc) => (
                    <option key={sc.key} value={sc.key}>
                      {sc.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Approval Threshold (₹)</label>
                <input
                  type="number"
                  className="form-input"
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                />
              </div>
            </div>
            <div className="control-footer">
              <div>
                {errorMsg && <span style={{ color: "#dc2626", fontWeight: 600, fontSize: "0.8rem" }}>{errorMsg}</span>}
              </div>
              <button
                className="btn-enterprise-primary"
                onClick={startInvestigation}
                disabled={loading || currentRun?.status === "running" || !goal.trim()}
              >
                {currentRun?.status === "running" ? "INVESTIGATING..." : "START INVESTIGATION"}
              </button>
            </div>
          </div>
        </section>

        {/* Process Progress Workflow Bar */}
        <div className="workflow-bar">
          <div className={`workflow-step ${currentRun ? "active" : ""}`}>
            <span className="workflow-step-num">1</span>
            <span>GOAL</span>
          </div>
          <span className="workflow-sep">➔</span>
          <div className={`workflow-step ${currentRun?.step_count ? "active" : ""}`}>
            <span className="workflow-step-num">2</span>
            <span>DECISION</span>
          </div>
          <span className="workflow-sep">➔</span>
          <div className={`workflow-step ${currentRun?.action_proposals.length ? "active" : ""}`}>
            <span className="workflow-step-num">3</span>
            <span>ACTION</span>
          </div>
          <span className="workflow-sep">➔</span>
          <div className={`workflow-step ${currentRun?.actions.length ? "active" : ""}`}>
            <span className="workflow-step-num">4</span>
            <span>RESULT</span>
          </div>
          <span className="workflow-sep">➔</span>
          <div className={`workflow-step ${currentRun?.events.some((e) => e.event_type === "adaptation") ? "active" : ""}`}>
            <span className="workflow-step-num">5</span>
            <span>ADAPTATION</span>
          </div>
          <span className="workflow-sep">➔</span>
          <div className={`workflow-step ${currentRun?.events.some((e) => e.event_type === "verification") ? "active" : ""}`}>
            <span className="workflow-step-num">6</span>
            <span>VERIFICATION</span>
          </div>
          <span className="workflow-sep">➔</span>
          <div className={`workflow-step ${currentRun?.status === "completed" ? "completed" : ""}`}>
            <span className="workflow-step-num">7</span>
            <span>OUTCOME</span>
          </div>
        </div>

        {/* Dashboard 2-Column Columns */}
        {currentRun && (
          <div className="dashboard-columns">
            {/* Left Column: Focus & Timeline Audit */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {/* Current Agent Focus Panel */}
              <div className="enterprise-panel">
                <div className="panel-header">
                  <span>CURRENT AGENT FOCUS</span>
                  <span className="panel-header-sub">
                    STATUS: <strong style={{ color: "#60a5fa" }}>{getStatusLabel()}</strong> | STEP {currentRun.step_count}
                  </span>
                </div>
                <div className="panel-body">
                  <div className="op-info-grid">
                    <div className="op-info-block">
                      <span className="op-info-label">CURRENT OBJECTIVE</span>
                      <span className="op-info-val">{currentRun.current_objective}</span>
                    </div>
                    <div className="op-info-block">
                      <span className="op-info-label">WORKING HYPOTHESIS</span>
                      <span className="op-info-val">{currentRun.current_hypothesis}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Execution Timeline Audit Table */}
              <div className="enterprise-panel">
                <div className="panel-header">
                  <span>EXECUTION TIMELINE AUDIT</span>
                  <span className="panel-header-sub">{currentRun.events.length} EVENTS RECORDED</span>
                </div>
                <div className="panel-body" style={{ padding: 0 }}>
                  <table className="enterprise-table">
                    <thead>
                      <tr>
                        <th style={{ width: "80px" }}>TIME</th>
                        <th style={{ width: "130px" }}>TYPE</th>
                        <th>EVENT SUMMARY & DETAILS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {currentRun.events.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="table-empty">
                            No execution events recorded yet.
                          </td>
                        </tr>
                      ) : (
                        currentRun.events.map((evt, idx) => (
                          <tr key={evt.sequence || idx}>
                            <td style={{ color: "#64748b", fontSize: "0.75rem" }}>
                              {formatTimestamp(evt.created_at || evt.timestamp)}
                            </td>
                            <td>
                              <span className={`badge badge-${evt.event_type}`}>
                                {evt.event_type.replace("_", " ")}
                              </span>
                            </td>
                            <td>{evt.summary}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Right Column: Customer Case, Approvals, Resolution, Verification, Evidence */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {/* Customer Case & Resolution Layer */}
              {currentRun.customer_case && (
                <div className="enterprise-panel" style={{ border: "1px solid #1e3a8a" }}>
                  <div className="panel-header" style={{ background: "#0f172a" }}>
                    <span>CUSTOMER CASE & RESOLUTION LAYER</span>
                    <span className="panel-header-sub" style={{ color: "#93c5fd" }}>
                      CASE ID: {currentRun.customer_case.case_id}
                    </span>
                  </div>
                  <div className="panel-body">
                    <div className="op-info-grid">
                      <div className="op-info-block">
                        <span className="op-info-label">ISSUE REPORTED</span>
                        <span className="op-info-val">{currentRun.customer_case.issue}</span>
                      </div>
                      <div className="op-info-block">
                        <span className="op-info-label">AFFECTED SERVICE</span>
                        <span className="op-info-val">{currentRun.customer_case.affected_service}</span>
                      </div>
                      <div className="op-info-block">
                        <span className="op-info-label">CUSTOMER IMPACT</span>
                        <span className="op-info-val" style={{ color: "#b91c1c", fontWeight: 700 }}>
                          {currentRun.customer_case.impact}
                        </span>
                      </div>
                      <div className="op-info-block">
                        <span className="op-info-label">CASE RESOLUTION STATUS</span>
                        <span
                          className="op-info-val"
                          style={{
                            color: currentRun.customer_case.status === "RESOLVED" ? "#166534" : "#1d4ed8",
                            fontWeight: 700,
                          }}
                        >
                          {currentRun.customer_case.status}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Human Approval Required Request Box */}
              {currentRun.status === "awaiting_approval" && currentRun.pending_action && (
                <div className="approval-panel-box">
                  <div className="approval-title">
                    <span>⚠️ ACTION REQUIRES HUMAN APPROVAL</span>
                  </div>
                  <div className="approval-details-grid">
                    <div>
                      <strong>Proposed Action:</strong> {currentRun.pending_action.action}
                    </div>
                    <div>
                      <strong>Risk Level:</strong>{" "}
                      <span style={{ color: "#b45309", fontWeight: 700 }}>
                        {currentRun.pending_action.permission_level.replace("_", " ").toUpperCase()}
                      </span>
                    </div>
                    <div style={{ gridColumn: "span 2" }}>
                      <strong>Reason:</strong> {currentRun.pending_action.reason}
                    </div>
                    <div style={{ gridColumn: "span 2" }}>
                      <strong>Risk Assessment:</strong> {currentRun.pending_action.risk}
                    </div>
                    <div style={{ gridColumn: "span 2" }}>
                      <strong>Estimated Impact:</strong> {JSON.stringify(currentRun.pending_action.estimated_impact)}
                    </div>
                  </div>
                  <div className="btn-group-approval">
                    <button className="btn-approve" onClick={() => submitApproval(true)} disabled={loading}>
                      ✓ APPROVE ACTION
                    </button>
                    <button className="btn-reject" onClick={() => submitApproval(false)} disabled={loading}>
                      ✕ REJECT ACTION
                    </button>
                  </div>
                </div>
              )}

              {/* Post-Action Verification State Comparison */}
              {verifiedProposal && verifiedProposal.verification && (
                <div className="enterprise-panel" style={{ border: "1px solid #0d9488" }}>
                  <div className="panel-header" style={{ background: "#115e59" }}>
                    <span>POST-ACTION VERIFICATION STATE COMPARISON</span>
                    <span className="panel-header-sub" style={{ color: "#ccfbf1" }}>
                      STATUS: {verifiedProposal.verification.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="panel-body" style={{ padding: 0 }}>
                    <div style={{ padding: "0.6rem 0.8rem", fontSize: "0.825rem", background: "#f0fdf4", color: "#166534", borderBottom: "1px solid #cbd5e1" }}>
                      <strong>Detail:</strong> {verifiedProposal.verification.detail}
                    </div>
                    <table className="enterprise-table">
                      <thead>
                        <tr>
                          <th>STATE PARAMETER</th>
                          <th>BEFORE ACTION</th>
                          <th>AFTER ACTION</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.keys(verifiedProposal.verification.before).map((key) => (
                          <tr key={key}>
                            <td style={{ fontWeight: 600 }}>{key}</td>
                            <td style={{ color: "#991b1b" }}>
                              {String(verifiedProposal.verification?.before[key] ?? "N/A")}
                            </td>
                            <td style={{ color: "#166534", fontWeight: 700 }}>
                              {String(verifiedProposal.verification?.after[key] ?? "N/A")} ✓
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Final Investigation Resolution */}
              {currentRun.status === "completed" && currentRun.final_result && (
                <div className="resolution-box">
                  <div className="resolution-title-row">
                    <span className="resolution-heading">✅ INVESTIGATION RESOLUTION</span>
                    <span className={`confidence-tag conf-${currentRun.final_result.confidence}`}>
                      CONFIDENCE: {currentRun.final_result.confidence.toUpperCase()}
                    </span>
                  </div>
                  <div className="resolution-text">
                    <strong>CONCLUSION / ROOT CAUSE:</strong>
                    <br />
                    {currentRun.final_result.conclusion}
                  </div>
                  {currentRun.final_result.actions_executed.length > 0 && (
                    <div style={{ fontSize: "0.8rem", color: "#1e40af" }}>
                      <strong>EXECUTED ACTIONS:</strong>
                      <ul style={{ margin: "0.2rem 0 0", paddingLeft: "1.2rem" }}>
                        {currentRun.final_result.actions_executed.map((act, idx) => (
                          <li key={idx}>{act}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {currentRun.final_result.unresolved_issues.length > 0 && (
                    <div style={{ fontSize: "0.8rem", color: "#92400e" }}>
                      <strong>UNRESOLVED ISSUES / VERIFICATION WARNINGS:</strong>
                      <ul style={{ margin: "0.2rem 0 0", paddingLeft: "1.2rem" }}>
                        {currentRun.final_result.unresolved_issues.map((issue, idx) => (
                          <li key={idx}>{issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Observed Evidence Audit Table */}
              <div className="enterprise-panel">
                <div className="panel-header">
                  <span>OBSERVED EVIDENCE</span>
                  <span className="panel-header-sub">{currentRun.evidence.length} FINDINGS CLASSIFIED</span>
                </div>
                <div className="panel-body" style={{ padding: 0 }}>
                  <table className="enterprise-table">
                    <thead>
                      <tr>
                        <th style={{ width: "160px" }}>SOURCE</th>
                        <th>OBSERVED FINDING / EVIDENCE</th>
                        <th style={{ width: "120px" }}>CLASSIFICATION</th>
                      </tr>
                    </thead>
                    <tbody>
                      {currentRun.evidence.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="table-empty">
                            No evidence collected yet.
                          </td>
                        </tr>
                      ) : (
                        currentRun.evidence.map((item, idx) => (
                          <tr key={idx}>
                            <td style={{ fontWeight: 600, color: "#1e293b" }}>{item.source}</td>
                            <td>{item.fact}</td>
                            <td>
                              <span
                                className={`badge ${
                                  item.kind === "hypothesis"
                                    ? "badge-hypothesis_update"
                                    : item.kind === "verified"
                                    ? "badge-verification"
                                    : "badge-tool_result"
                                }`}
                              >
                                {item.kind === "hypothesis"
                                  ? "HYPOTHESIS"
                                  : item.kind === "verified"
                                  ? "VERIFIED RESULT"
                                  : "OBSERVED FACT"}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Post-Action Verification Log */}
              {currentRun.verification_notes.length > 0 && (
                <div className="enterprise-panel">
                  <div className="panel-header">
                    <span>POST-ACTION VERIFICATION LOG</span>
                  </div>
                  <div className="panel-body" style={{ fontSize: "0.825rem" }}>
                    {currentRun.verification_notes.map((note, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: "0.35rem 0",
                          borderBottom: "1px solid var(--border-light)",
                          color: "#1e293b",
                        }}
                      >
                        • {note}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
