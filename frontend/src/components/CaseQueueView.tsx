import React, { useState } from "react";

export interface Scenario {
  key: string;
  name: string;
  description: string;
  customer_case?: {
    case_id: string;
    customer_id?: string;
    order_id?: string;
    issue: string;
    impact?: string;
    affected_service?: string;
    status: string;
  };
}

export interface AgentRunState {
  run_id: string;
  original_goal: string;
  customer_case?: {
    case_id: string;
    customer_id?: string;
    order_id?: string;
    issue: string;
    requested_resolution?: string;
    status: string;
  };
  step_count: number;
  status: string;
}

interface CaseQueueViewProps {
  scenarios: Scenario[];
  runs: AgentRunState[];
  selectedScenario: string;
  onScenarioChange: (key: string) => void;
  goal: string;
  setGoal: (g: string) => void;
  threshold: string;
  setThreshold: (t: string) => void;
  onStartRun: () => void;
  onSelectRun: (runId: string) => void;
  loading: boolean;
}

export const CaseQueueView: React.FC<CaseQueueViewProps> = ({
  scenarios,
  runs,
  selectedScenario,
  onScenarioChange,
  goal,
  setGoal,
  threshold,
  setThreshold,
  onStartRun,
  onSelectRun,
  loading,
}) => {
  const activeScenarioObj = scenarios.find((s) => s.key === selectedScenario);

  // Compute metrics from active runs
  const totalRuns = runs.length;
  const awaitingRuns = runs.filter((r) => r.status === "awaiting_approval" || r.customer_case?.status === "AWAITING_APPROVAL").length;
  const resolvedRuns = runs.filter((r) => r.status === "completed" || r.customer_case?.status === "RESOLVED").length;
  const escalatedRuns = runs.filter((r) => r.customer_case?.status === "ESCALATED").length;
  const activeRuns = runs.filter((r) => r.status === "running" || r.customer_case?.status === "INVESTIGATING").length;

  return (
    <div className="queue-container">
      {/* Metrics Banner */}
      <div className="metrics-banner-grid">
        <div className="metric-card">
          <span className="metric-num">{totalRuns}</span>
          <span className="metric-label">Total Resolution Cases</span>
        </div>
        <div className="metric-card">
          <span className="metric-num text-info">{activeRuns}</span>
          <span className="metric-label">Investigating / Running</span>
        </div>
        <div className="metric-card">
          <span className="metric-num text-warning">{awaitingRuns}</span>
          <span className="metric-label">Awaiting Approval</span>
        </div>
        <div className="metric-card">
          <span className="metric-num text-success">{resolvedRuns}</span>
          <span className="metric-label">Verified Resolved</span>
        </div>
        <div className="metric-card">
          <span className="metric-num text-purple">{escalatedRuns}</span>
          <span className="metric-label">Escalated to Human</span>
        </div>
      </div>

      {/* New Case Creation Box */}
      <div className="enterprise-panel">
        <div className="panel-header">
          <span>Launch New Autonomous Resolution Case</span>
          <span className="panel-header-sub">Track 3 — PS5 Agent Dispatcher</span>
        </div>
        <div className="panel-body">
          <div className="form-group mb-3">
            <label className="form-label font-bold text-accent">Customer Issue / Natural-Language Goal (Primary Intent)</label>
            <input
              className="form-input text-lg"
              type="text"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="Describe the customer's issue and desired outcome (e.g. 'My laptop stand arrived damaged. I want a replacement.')..."
            />
          </div>

          <div className="control-grid">
            <div className="form-group">
              <label className="form-label">Simulation Environment / World Scenario (Demo Data & Failure Plans)</label>
              <select
                className="form-select"
                value={selectedScenario}
                onChange={(e) => onScenarioChange(e.target.value)}
              >
                <optgroup label="PS5 Autonomous Customer Resolution Scenarios">
                  {scenarios
                    .filter((s) => s.key.startsWith("customer_"))
                    .map((s) => (
                      <option key={s.key} value={s.key}>
                        {s.name}
                      </option>
                    ))}
                </optgroup>
                <optgroup label="Operational Investigation Scenarios">
                  {scenarios
                    .filter((s) => !s.key.startsWith("customer_"))
                    .map((s) => (
                      <option key={s.key} value={s.key}>
                        {s.name}
                      </option>
                    ))}
                </optgroup>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Approval Threshold (INR)</label>
              <input
                className="form-input"
                type="number"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                placeholder="5000"
              />
            </div>
          </div>

          {activeScenarioObj?.customer_case && (
            <div className="scenario-preview-box">
              <span className="preview-label">Simulation World State Data:</span>
              <div className="preview-tags">
                <span className="tag font-mono">{activeScenarioObj.customer_case.case_id}</span>
                <span className="tag">{activeScenarioObj.customer_case.customer_id || "Customer"}</span>
                <span className="tag">{activeScenarioObj.customer_case.order_id || "Order"}</span>
                <span className="tag highlight">{activeScenarioObj.customer_case.issue}</span>
              </div>
            </div>
          )}

          <div className="control-footer">
            <button
              type="button"
              className="btn-enterprise-primary"
              onClick={onStartRun}
              disabled={loading}
            >
              {loading ? "Initializing..." : "Create & Open Case Workspace →"}
            </button>
          </div>
        </div>
      </div>

      {/* Case Queue Table */}
      <div className="enterprise-panel">
        <div className="panel-header">
          <span>Customer Resolution Case Queue</span>
          <span className="panel-header-sub">{runs.length} Active / Past Cases</span>
        </div>
        <div className="panel-body">
          {runs.length > 0 ? (
            <table className="enterprise-table">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Customer ID</th>
                  <th>Order ID</th>
                  <th>Reported Issue</th>
                  <th>Steps</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => {
                  const statusStr = r.customer_case?.status || r.status.toUpperCase();
                  return (
                    <tr key={r.run_id} className="queue-row">
                      <td className="font-mono font-bold">
                        {r.customer_case?.case_id || r.run_id.slice(0, 8)}
                      </td>
                      <td>{r.customer_case?.customer_id || "Customer"}</td>
                      <td className="font-mono">{r.customer_case?.order_id || "—"}</td>
                      <td>{r.customer_case?.issue || r.original_goal}</td>
                      <td>{r.step_count}</td>
                      <td>
                        <span className={`badge badge-${statusStr.toLowerCase()}`}>
                          {statusStr}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-enterprise-sm"
                          onClick={() => onSelectRun(r.run_id)}
                        >
                          Open Workspace →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="table-empty">
              No active customer cases in queue yet. Launch a new case using the control above!
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
