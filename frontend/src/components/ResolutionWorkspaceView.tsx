import React from "react";

export interface VerificationOutcome {
  status: "verified" | "failed" | "inconclusive";
  detail: string;
  before: Record<string, any>;
  after: Record<string, any>;
}

export interface ActionProposal {
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

export interface AgentEvent {
  sequence?: number;
  event_type: string;
  summary: string;
  created_at?: string;
  timestamp?: string;
  tool_name?: string;
}

export interface ToolHistoryEntry {
  step: number;
  reasoning: string;
  hypothesis: string;
  tool_call: { name: string; arguments: Record<string, any> };
  result: { ok: boolean; summary: string; data?: Record<string, any>; error?: any };
}

export interface AgentState {
  run_id: string;
  original_goal: string;
  customer_case?: {
    case_id: string;
    customer_id?: string;
    order_id?: string;
    issue: string;
    requested_resolution?: string;
    status: string;
    final_resolution?: string;
  };
  current_objective: string;
  current_hypothesis: string;
  evidence: Array<{ source: string; fact: string }>;
  tool_history?: ToolHistoryEntry[];
  failures: string[];
  actions: string[];
  action_proposals: ActionProposal[];
  pending_action: ActionProposal | null;
  events: AgentEvent[];
  status: "running" | "awaiting_approval" | "completed" | "failed" | "timed_out" | "step_limit_reached";
  final_result: {
    conclusion: string;
    confidence: string;
    unresolved_issues: string[];
    actions_executed: string[];
  } | null;
  step_count: number;
}

interface ResolutionWorkspaceViewProps {
  currentRun: AgentState | null;
  onBackToQueue: () => void;
  onSubmitApproval: (approved: boolean) => void;
  onStartExecution?: (runId: string) => void;
  loading: boolean;
}

function formatTimestamp(tsString?: string): string {
  if (!tsString) return "—";
  const d = new Date(tsString);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-US", { hour12: false });
}

export const ResolutionWorkspaceView: React.FC<ResolutionWorkspaceViewProps> = ({
  currentRun,
  onBackToQueue,
  onSubmitApproval,
  onStartExecution,
  loading,
}) => {
  if (!currentRun) {
    return (
      <div className="enterprise-panel">
        <div className="panel-body text-center" style={{ padding: "3rem" }}>
          <h3>No Customer Case Workspace Selected</h3>
          <p className="muted" style={{ marginTop: "0.5rem" }}>
            Select an existing case from the Customer Case Queue or launch a new case.
          </p>
          <button
            type="button"
            className="btn-enterprise-primary"
            onClick={onBackToQueue}
            style={{ marginTop: "1rem" }}
          >
            ← Go to Customer Case Queue
          </button>
        </div>
      </div>
    );
  }

  // Extract case and agent execution statuses
  const getCaseStatus = () => {
    if (currentRun.customer_case?.status) return currentRun.customer_case.status;
    if (currentRun.status === "awaiting_approval") return "AWAITING_APPROVAL";
    if (currentRun.status === "completed") return "RESOLVED";
    if (currentRun.status === "failed") return "FAILED";
    return currentRun.step_count === 0 ? "OPEN" : "INVESTIGATING";
  };

  const statusStr = getCaseStatus();

  const getAgentExecutionStatusLabel = () => {
    if (currentRun.status === "awaiting_approval") return "AWAITING APPROVAL";
    if (currentRun.customer_case?.status === "VERIFYING") return "VERIFYING Baseline Diff";
    if (currentRun.status === "completed") return statusStr === "RESOLVED" ? "RESOLVED" : "COMPLETED";
    if (currentRun.status === "failed") return "FAILED";
    if (currentRun.step_count === 0 && (statusStr === "OPEN" || currentRun.status === "running")) {
      return "READY TO INVESTIGATE";
    }
    return `RUNNING (Step ${currentRun.step_count})`;
  };

  const agentExecutionLabel = getAgentExecutionStatusLabel();

  // Extract structured tool data from tool_history
  const findToolData = (toolName: string) => {
    if (!currentRun.tool_history) return null;
    const entry = [...currentRun.tool_history].reverse().find((e) => e.tool_call.name === toolName && e.result.ok);
    return entry?.result?.data || null;
  };

  const customerData = findToolData("get_customer")?.customer;
  const orderData = findToolData("get_order")?.order;
  const eligibilityData = findToolData("check_customer_resolution_eligibility");
  const inventoryData = findToolData("get_customer_inventory");
  const policyData = findToolData("get_policy")?.policies;

  const verifiedProposal = currentRun.action_proposals.find((p) => p.verification != null);

  const canStartRun =
    currentRun.step_count === 0 &&
    (currentRun.status === "running" || (currentRun as any).status === "created") &&
    (statusStr === "OPEN" || currentRun.customer_case?.status === "OPEN") &&
    Boolean(onStartExecution);

  return (
    <div className="workspace-container">
      {/* Workspace Bar */}
      <div className="workspace-header-bar">
        <button type="button" className="btn-enterprise-back" onClick={onBackToQueue}>
          ← Back to Cases
        </button>

        <div className="workspace-title-group">
          <span className="case-id-badge font-mono">
            {currentRun.customer_case?.case_id || "CS-CASE"}
          </span>
          <h2 className="workspace-title">
            {customerData?.name ? `${customerData.name} — ` : ""}
            {currentRun.customer_case?.issue || currentRun.original_goal}
          </h2>
        </div>

        <div className="workspace-status-tags" style={{ gap: "0.5rem" }}>
          <span className="form-label">Case Status:</span>
          <span className={`badge badge-${statusStr.toLowerCase()}`}>{statusStr}</span>
          <span className="form-label" style={{ marginLeft: "0.5rem" }}>Agent:</span>
          <span className={`badge badge-${currentRun.status === "running" && currentRun.step_count > 0 ? "investigating" : currentRun.status.toLowerCase()}`}>
            {agentExecutionLabel}
          </span>
        </div>

        {canStartRun && (
          <button
            type="button"
            className="btn-enterprise-primary"
            onClick={() => onStartExecution!(currentRun.run_id)}
            disabled={loading}
            style={{ marginLeft: "auto", padding: "0.5rem 1.25rem" }}
          >
            {loading ? "Initializing..." : "🚀 Start Autonomous Investigation"}
          </button>
        )}
      </div>

      {/* 8-Stage Workflow Stepper */}
      <div className="workflow-bar">
        <div className={`workflow-step ${currentRun ? "completed" : ""}`}>
          <span className="workflow-step-num">1</span>
          <span>GOAL</span>
        </div>
        <span className="workflow-sep">→</span>

        <div className={`workflow-step ${currentRun.step_count ? (statusStr === "INVESTIGATING" ? "active" : "completed") : ""}`}>
          <span className="workflow-step-num">2</span>
          <span>INVESTIGATION</span>
        </div>
        <span className="workflow-sep">→</span>

        <div className={`workflow-step ${currentRun.evidence.length ? (statusStr === "INVESTIGATING" ? "active" : "completed") : ""}`}>
          <span className="workflow-step-num">3</span>
          <span>EVIDENCE</span>
        </div>
        <span className="workflow-sep">→</span>

        <div className={`workflow-step ${currentRun.current_hypothesis ? "completed" : ""}`}>
          <span className="workflow-step-num">4</span>
          <span>DECISION</span>
        </div>
        <span className="workflow-sep">→</span>

        <div className={`workflow-step ${currentRun.action_proposals.length ? (statusStr === "ACTION_IN_PROGRESS" || statusStr === "AWAITING_APPROVAL" ? "active" : "completed") : ""}`}>
          <span className="workflow-step-num">5</span>
          <span>ACTION</span>
        </div>
        <span className="workflow-sep">→</span>

        <div className={`workflow-step ${verifiedProposal ? (statusStr === "VERIFYING" ? "active" : "completed") : ""}`}>
          <span className="workflow-step-num">6</span>
          <span>VERIFICATION</span>
        </div>
        <span className="workflow-sep">→</span>

        <div className={`workflow-step ${currentRun.events.some((e) => e.event_type === "adaptation") ? "completed" : ""}`}>
          <span className="workflow-step-num">7</span>
          <span>ADAPTATION</span>
        </div>
        <span className="workflow-sep">→</span>

        <div className={`workflow-step ${statusStr === "RESOLVED" || statusStr === "ESCALATED" || statusStr === "FAILED" ? "completed" : ""}`}>
          <span className="workflow-step-num">8</span>
          <span>OUTCOME</span>
        </div>
      </div>

      {/* 2-Column Responsive Workspace Grid */}
      <div className="workspace-two-column-grid">
        {/* LEFT COLUMN: CUSTOMER & CASE CONTEXT */}
        <div className="workspace-column">
          {/* Card 1: CUSTOMER PROFILE & HISTORY */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>1. CUSTOMER PROFILE & HISTORY</span>
              <span className="badge badge-vip">{customerData?.tier || "Pending"}</span>
            </div>
            <div className="panel-body compact">
              <div className="data-row">
                <span className="data-label">Customer ID / Name:</span>
                <span className="data-val font-bold">
                  {customerData?.customer_id || currentRun.customer_case?.customer_id || "Awaiting lookup..."}
                  {customerData?.name ? ` (${customerData.name})` : ""}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">Email:</span>
                <span className="data-val">{customerData?.email || "Awaiting investigation..."}</span>
              </div>
              <div className="data-row">
                <span className="data-label">Total Orders:</span>
                <span className="data-val">{customerData?.total_orders !== undefined ? customerData.total_orders : "—"}</span>
              </div>
              <div className="data-row">
                <span className="data-label">Lifetime Spent:</span>
                <span className="data-val font-bold">
                  {customerData?.total_spent_inr !== undefined ? `₹${customerData.total_spent_inr.toLocaleString()}` : "—"}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">History Summary:</span>
                <span className="data-val muted">
                  {customerData?.history_summary || "Customer history will load when get_customer is executed."}
                </span>
              </div>
            </div>
          </div>

          {/* Card 2: ORDER DETAILS & FULFILLMENT */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>2. ORDER DETAILS & FULFILLMENT</span>
              <span className="panel-header-sub">{orderData?.order_id || currentRun.customer_case?.order_id || "Awaiting lookup..."}</span>
            </div>
            <div className="panel-body compact">
              <div className="data-row">
                <span className="data-label">Product SKU:</span>
                <span className="data-val font-bold">
                  {orderData?.product_id ? `${orderData.product_id} (${orderData.product_name || "Product"})` : "Awaiting lookup..."}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">Price:</span>
                <span className="data-val font-bold">
                  {orderData?.price !== undefined ? `₹${orderData.price.toLocaleString()}` : "—"}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">Order Status:</span>
                <span className="badge badge-tool_result">{orderData?.status || "Pending"}</span>
              </div>
              <div className="data-row">
                <span className="data-label">Fulfillment Status:</span>
                <span className="data-val">{orderData?.fulfillment_status || "—"}</span>
              </div>
              <div className="data-row">
                <span className="data-label">Resolution States:</span>
                <span className="data-val muted">
                  {orderData ? `Refund: ${orderData.refund_state || "none"} | Replacement: ${orderData.replacement_state || "none"}` : "Awaiting order lookup..."}
                </span>
              </div>
            </div>
          </div>

          {/* Card 3: POLICY & ELIGIBILITY CONSTRAINTS */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>3. POLICY & ELIGIBILITY CONSTRAINTS</span>
              <span className="panel-header-sub">Deterministic Policy Engine</span>
            </div>
            <div className="panel-body compact">
              <div className="data-row">
                <span className="data-label">Eligibility Result:</span>
                <span className={`badge ${eligibilityData?.eligible ? "badge-completed" : "badge-tool_error"}`}>
                  {eligibilityData?.eligible !== undefined ? (eligibilityData.eligible ? "ELIGIBLE" : "NOT ELIGIBLE") : "AWAITING CHECK"}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">Approval Requirement:</span>
                <span className="data-val">
                  {eligibilityData ? (eligibilityData.requires_human_approval ? "Requires Human Approval (>= ₹5,000)" : "Auto-Approval Permitted") : "Pending policy check"}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">Constraint Block:</span>
                <span className="data-val danger">{eligibilityData?.blocked_by ? `Blocked by: ${eligibilityData.blocked_by}` : "None"}</span>
              </div>
              <div className="data-row">
                <span className="data-label">Policy Rule:</span>
                <span className="data-val muted">
                  {eligibilityData?.reason || policyData?.refund_policy?.approval_rule || "Policy rules will load when get_policy is executed."}
                </span>
              </div>
            </div>
          </div>

          {/* Card 4: INVENTORY AVAILABILITY */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>4. INVENTORY AVAILABILITY</span>
              <span className="panel-header-sub">{inventoryData?.product_id || "Awaiting check..."}</span>
            </div>
            <div className="panel-body compact">
              <div className="data-row">
                <span className="data-label">Stock Status:</span>
                <span className={`badge ${inventoryData?.in_stock !== false ? "badge-completed" : "badge-tool_error"}`}>
                  {inventoryData?.in_stock !== undefined ? (inventoryData.in_stock ? "IN STOCK" : "OUT OF STOCK") : "AWAITING CHECK"}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">Available for Replacement:</span>
                <span className="data-val font-bold">
                  {inventoryData?.available_for_replacement !== undefined ? `${inventoryData.available_for_replacement} units` : "—"}
                </span>
              </div>
              <div className="data-row">
                <span className="data-label">On Hand / Reserved:</span>
                <span className="data-val">
                  {inventoryData ? `${inventoryData.on_hand} on hand / ${inventoryData.reserved} reserved` : "Awaiting inventory lookup"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: AGENT RESOLUTION EXECUTION */}
        <div className="workspace-column">
          {/* Card 5: DECISION ENGINE & HYPOTHESIS */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>5. DECISION ENGINE & RATIONALE</span>
              <span className="panel-header-sub">Evidence-Driven Policy</span>
            </div>
            <div className="panel-body compact">
              <div className="data-row">
                <span className="data-label">Current Objective:</span>
                <span className="data-val">{currentRun.current_objective || "Understand the reported customer issue."}</span>
              </div>
              <div className="data-row">
                <span className="data-label">Current Hypothesis:</span>
                <span className="data-val muted">{currentRun.current_hypothesis || "Formulating hypothesis from evidence..."}</span>
              </div>
              <div className="data-row">
                <span className="data-label">Selected Remediation:</span>
                <span className="data-val font-bold highlight">
                  {currentRun.action_proposals.length ? currentRun.action_proposals[0].action : "Evaluating resolution paths..."}
                </span>
              </div>
            </div>
          </div>

          {/* Card 6: REMEDIATION ACTION & APPROVAL */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>6. REMEDIATION ACTION & APPROVAL</span>
              <span className="panel-header-sub">Permission Gate</span>
            </div>
            <div className="panel-body compact">
              {currentRun.status === "awaiting_approval" && currentRun.pending_action ? (
                <div className="approval-panel-box">
                  <div className="approval-title">
                    ⚠️ HUMAN APPROVAL REQUIRED FOR HIGH-RISK ACTION
                  </div>
                  <div className="approval-details-grid">
                    <div><strong>Action:</strong> {currentRun.pending_action.action}</div>
                    <div><strong>Permission Level:</strong> {currentRun.pending_action.permission_level}</div>
                    <div><strong>Risk Level:</strong> {currentRun.pending_action.risk}</div>
                    <div><strong>Reason:</strong> {currentRun.pending_action.reason}</div>
                  </div>
                  <div className="btn-group-approval">
                    <button type="button" className="btn-approve" onClick={() => onSubmitApproval(true)} disabled={loading}>
                      Approve & Execute Action
                    </button>
                    <button type="button" className="btn-reject" onClick={() => onSubmitApproval(false)} disabled={loading}>
                      Reject Action
                    </button>
                  </div>
                </div>
              ) : currentRun.action_proposals && currentRun.action_proposals.length > 0 ? (
                <div>
                  <div className="data-row">
                    <span className="data-label">Action Executed:</span>
                    <span className="data-val font-bold">{currentRun.action_proposals[0].action}</span>
                  </div>
                  <div className="data-row">
                    <span className="data-label">Permission Level:</span>
                    <span className="badge badge-tool_result">{currentRun.action_proposals[0].permission_level}</span>
                  </div>
                  <div className="data-row">
                    <span className="data-label">Outcome Summary:</span>
                    <span className="data-val muted">{currentRun.action_proposals[0].outcome_summary || "Simulated action executed; verification complete."}</span>
                  </div>
                </div>
              ) : (
                <div className="table-empty">No remediation action proposed yet.</div>
              )}
            </div>
          </div>

          {/* Card 7: POST-ACTION VERIFICATION */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>7. POST-ACTION VERIFICATION</span>
              <span className="panel-header-sub">Baseline State Diff</span>
            </div>
            <div className="panel-body compact">
              {verifiedProposal?.verification ? (
                <div>
                  <div className="data-row">
                    <span className="data-label">Verification Outcome:</span>
                    <span className={`badge ${verifiedProposal.verification.status === "verified" ? "badge-completed" : "badge-tool_error"}`}>
                      {verifiedProposal.verification.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="data-row">
                    <span className="data-label">Verification Detail:</span>
                    <span className="data-val">{verifiedProposal.verification.detail}</span>
                  </div>
                  <div className="op-info-grid" style={{ marginTop: "0.5rem" }}>
                    <div className="op-info-block">
                      <span className="op-info-label">Pre-Action Baseline:</span>
                      <span className="op-info-val font-mono">{JSON.stringify(verifiedProposal.verification.before)}</span>
                    </div>
                    <div className="op-info-block">
                      <span className="op-info-label">Post-Action State:</span>
                      <span className="op-info-val font-mono">{JSON.stringify(verifiedProposal.verification.after)}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="table-empty">Post-action verification will run after action execution.</div>
              )}
            </div>
          </div>

          {/* Card 8: FINAL CASE RESOLUTION */}
          <div className="enterprise-panel card-panel">
            <div className="panel-header">
              <span>8. FINAL CASE RESOLUTION & TERMINAL OUTCOME</span>
              <span className={`badge badge-${statusStr.toLowerCase()}`}>{statusStr}</span>
            </div>
            <div className="panel-body">
              {currentRun.final_result ? (
                <div className="resolution-box">
                  <div className="resolution-title-row">
                    <span className="resolution-heading">Terminal Status: {statusStr}</span>
                    <span className={`confidence-tag conf-${currentRun.final_result.confidence}`}>
                      Confidence: {currentRun.final_result.confidence}
                    </span>
                  </div>

                  <div className="resolution-text">
                    <strong>Resolution Summary:</strong> {currentRun.customer_case?.final_resolution || currentRun.final_result.conclusion}
                  </div>

                  {currentRun.final_result.unresolved_issues.length > 0 && (
                    <div className="unresolved-issues-block" style={{ marginTop: "0.5rem" }}>
                      <strong>Unresolved Issues:</strong>
                      <ul>
                        {currentRun.final_result.unresolved_issues.map((issue, idx) => (
                          <li key={idx} className="text-danger">{issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="table-empty">Investigation in progress... Final resolution will display here upon verified completion or escalation.</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* FULL-WIDTH BOTTOM PANEL: CHRONOLOGICAL AGENT ACTIVITY LOG */}
      <div className="enterprise-panel full-width">
        <div className="panel-header">
          <span>9. CHRONOLOGICAL AGENT ACTIVITY LOG (TOOLS, FAILURES & ADAPTATION)</span>
          <span className="panel-header-sub">{currentRun.events.length} Recorded Events</span>
        </div>
        <div className="panel-body scrollable">
          {currentRun.events && currentRun.events.length > 0 ? (
            <table className="enterprise-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Type</th>
                  <th>Target Tool</th>
                  <th>Summary & Concise Evidence</th>
                </tr>
              </thead>
              <tbody>
                {currentRun.events.map((evt, idx) => (
                  <tr key={evt.sequence || idx}>
                    <td className="font-mono">{formatTimestamp(evt.created_at || evt.timestamp)}</td>
                    <td><span className={`badge badge-${evt.event_type}`}>{evt.event_type}</span></td>
                    <td className="font-mono">{evt.tool_name || "—"}</td>
                    <td>{evt.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="table-empty">No investigation activity recorded yet.</div>
          )}
        </div>
      </div>
    </div>
  );
};
