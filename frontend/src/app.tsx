import React, { useEffect, useState } from "react";
import "./styles.css";

import { Header } from "./components/Header";
import { LlmSettingsDrawer } from "./components/LlmSettingsDrawer";
import { CaseQueueView, Scenario, AgentRunState } from "./components/CaseQueueView";
import { ResolutionWorkspaceView } from "./components/ResolutionWorkspaceView";

interface LLMConfig {
  provider?: string | null;
  model?: string | null;
  base_url?: string | null;
  is_configured: boolean;
  has_api_key: boolean;
  connection_status: string;
  status_message?: string | null;
}

const API_BASE = "/api";

const DEFAULT_GOALS: Record<string, string> = {
  // PS5 Customer Resolution Scenarios
  customer_damaged_replacement_available: "My laptop stand arrived damaged in order ORD-9002. I want a replacement.",
  customer_replacement_out_of_stock_adapts_refund: "My product in order ORD-9003 arrived defective. Please replace it.",
  customer_refund_denied_policy_escalation: "I want to cancel my order ORD-9004 because I no longer need it.",
  customer_wrong_product_received: "I ordered Phone 1 but received Phone 2 in order ORD-9001. I want the correct phone.",
  customer_wrong_product_stockout_adapts: "I ordered Phone 1 but received Phone 2 in order ORD-9001. I want a replacement.",
  customer_inconclusive_image_log_lookup: "My product arrived damaged in order ORD-9001.",
  customer_ownership_mismatch_escalates: "Check resolution options for order ORD-9004 for customer CUST-801.",
  customer_investigation_tool_failure_adapts: "My product in order ORD-9001 arrived defective and I need help.",

  // Operational Scenarios
  inventory_supplier_failure: "Revenue dropped significantly today. Investigate why and resolve it if possible.",
  payment_failure: "Payment gateway timeouts are reported. Investigate and restore transaction health.",
  deployment_service_failure: "Checkout error rate spiked after release DEP-502. Investigate why and fix it if possible.",
  misleading_initial_hypothesis: "Investigate checkout cart abandonment and pricing anomalies.",
};

export default function App() {
  const [activeView, setActiveView] = useState<"queue" | "workspace">("queue");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [runs, setRuns] = useState<AgentRunState[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("customer_damaged_replacement_available");
  const [goal, setGoal] = useState<string>(DEFAULT_GOALS["customer_damaged_replacement_available"]);
  const [threshold, setThreshold] = useState<string>("5000");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [currentRun, setCurrentRun] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [systemHealth, setSystemHealth] = useState<{ status: string; llm_configured: boolean } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // LLM Drawer state
  const [showLlmDrawer, setShowLlmDrawer] = useState<boolean>(false);
  const [llmConfig, setLlmConfig] = useState<LLMConfig>({
    provider: null,
    model: null,
    base_url: null,
    is_configured: false,
    has_api_key: false,
    connection_status: "not_configured",
    status_message: "LLM is not configured. Running in deterministic fallback mode.",
  });
  const [llmSaving, setLlmSaving] = useState<boolean>(false);

  // Load initial health, LLM config, scenarios, and runs list
  const refreshData = async () => {
    try {
      const healthRes = await fetch(`${API_BASE}/health`);
      setSystemHealth(await healthRes.json());
    } catch {
      setSystemHealth({ status: "offline", llm_configured: false });
    }

    try {
      const llmRes = await fetch(`${API_BASE}/llm/config`);
      setLlmConfig(await llmRes.json());
    } catch (err) {
      console.error("Fetch LLM config failed:", err);
    }

    try {
      const scRes = await fetch(`${API_BASE}/scenarios`);
      const scData = await scRes.json();
      if (Array.isArray(scData) && scData.length > 0) {
        setScenarios(scData);
      }
    } catch (err) {
      console.error("Fetch scenarios failed:", err);
    }

    try {
      const runsRes = await fetch(`${API_BASE}/runs`);
      const runsData = await runsRes.json();
      if (Array.isArray(runsData)) {
        setRuns(runsData);
      }
    } catch (err) {
      console.error("Fetch runs failed:", err);
    }
  };

  useEffect(() => {
    refreshData();
  }, []);

  const handleScenarioChange = (key: string) => {
    setSelectedScenario(key);
    if (DEFAULT_GOALS[key]) {
      setGoal(DEFAULT_GOALS[key]);
    }
  };

  // Poll active run state every 500ms when status === "running"
  useEffect(() => {
    if (!activeRunId) return;
    const interval = setInterval(() => {
      fetch(`${API_BASE}/runs/${activeRunId}`)
        .then((res) => {
          if (!res.ok) throw new Error("Fetch run failed");
          return res.json();
        })
        .then((updated) => {
          setCurrentRun(updated);
          // Also update in runs array
          setRuns((prev) =>
            prev.map((r) => (r.run_id === updated.run_id ? updated : r))
          );
        })
        .catch((err) => console.error("Poll error:", err));
    }, 500);
    return () => clearInterval(interval);
  }, [activeRunId]);

  const createCustomerCase = async (attachmentFiles?: File[]) => {
    if (!goal.trim()) {
      setErrorMsg("Provide a non-empty customer resolution goal.");
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
          step_delay_seconds: 0.6,
          auto_start: false,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create customer case");
      }
      const data = await res.json();

      const caseId = data.customer_case?.case_id;
      if (caseId && attachmentFiles && attachmentFiles.length > 0) {
        for (const file of attachmentFiles) {
          const fileFormData = new FormData();
          fileFormData.append("file", file);
          await fetch(`${API_BASE}/cases/${caseId}/attachments`, {
            method: "POST",
            body: fileFormData,
          });
        }
        const runRes = await fetch(`${API_BASE}/runs/${data.run_id}`);
        if (runRes.ok) {
          const updatedRun = await runRes.json();
          setCurrentRun(updatedRun);
        } else {
          setCurrentRun(data);
        }
      } else {
        setCurrentRun(data);
      }

      setActiveRunId(data.run_id);
      setRuns((prev) => [data, ...prev.filter((r) => r.run_id !== data.run_id)]);
      setActiveView("workspace");
    } catch (err: any) {
      setErrorMsg(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  const startRunExecution = async (runId?: string) => {
    const targetRunId = runId || activeRunId;
    if (!targetRunId) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/runs/${targetRunId}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_delay_seconds: 0.6 }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to start autonomous investigation agent");
      }
      const data = await res.json();
      setCurrentRun(data);
      setActiveRunId(data.run_id);
      setRuns((prev) => prev.map((r) => (r.run_id === data.run_id ? data : r)));
    } catch (err: any) {
      setErrorMsg(err.message || "An unexpected error occurred while starting investigation");
    } finally {
      setLoading(false);
    }
  };

  const selectRunForWorkspace = async (runId: string) => {
    setActiveRunId(runId);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}`);
      if (!res.ok) throw new Error("Failed to fetch run details.");
      const data = await res.json();
      setCurrentRun(data);
      setActiveView("workspace");
    } catch (err: any) {
      setErrorMsg("Unable to open workspace for selected case.");
    } finally {
      setLoading(false);
    }
  };

  const submitApproval = async (approved: boolean) => {
    if (!activeRunId) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/runs/${activeRunId}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved, step_delay_seconds: 0.6 }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Approval decision failed");
      }
      const updated = await res.json();
      setCurrentRun(updated);
      setRuns((prev) =>
        prev.map((r) => (r.run_id === updated.run_id ? updated : r))
      );
    } catch (err: any) {
      setErrorMsg(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  const saveLlmConfig = async (payload: {
    provider: string;
    model: string;
    base_url: string;
    api_key?: string;
  }) => {
    setLlmSaving(true);
    setErrorMsg(null);
    try {
      const body: any = { ...payload, test_connection: true };
      const res = await fetch(`${API_BASE}/llm/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data: LLMConfig = await res.json();
      setLlmConfig(data);
      const healthRes = await fetch(`${API_BASE}/health`);
      setSystemHealth(await healthRes.json());
    } catch (err: any) {
      setErrorMsg("Failed to save LLM configuration.");
    } finally {
      setLlmSaving(false);
    }
  };

  const resetLlmConfig = async () => {
    setLlmSaving(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/llm/config`, { method: "DELETE" });
      const data: LLMConfig = await res.json();
      setLlmConfig(data);
      const healthRes = await fetch(`${API_BASE}/health`);
      setSystemHealth(await healthRes.json());
    } catch (err: any) {
      setErrorMsg("Failed to reset LLM configuration.");
    } finally {
      setLlmSaving(false);
    }
  };

  const [isPresentationMode, setIsPresentationMode] = useState<boolean>(false);

  return (
    <div className={`app-shell ${isPresentationMode ? "presentation-mode" : ""}`}>
      {/* Header Bar */}
      <Header
        activeView={activeView}
        setActiveView={setActiveView}
        llmConfig={llmConfig}
        systemHealth={systemHealth}
        onOpenLlmSettings={() => setShowLlmDrawer(true)}
        hasActiveRun={Boolean(currentRun && currentRun.status === "running")}
        isPresentationMode={isPresentationMode}
        onTogglePresentationMode={() => setIsPresentationMode(!isPresentationMode)}
      />

      {/* Main Content Area */}
      <main className="main-container">
        {/* System Error Alert */}
        {errorMsg && (
          <div className="alert-box error">
            <span><strong>System Notice:</strong> {errorMsg}</span>
            <button type="button" className="alert-close" onClick={() => setErrorMsg(null)}>×</button>
          </div>
        )}

        {/* Page 1: Customer Case Queue */}
        {activeView === "queue" && (
          <CaseQueueView
            scenarios={scenarios}
            runs={runs}
            selectedScenario={selectedScenario}
            onScenarioChange={handleScenarioChange}
            goal={goal}
            setGoal={setGoal}
            threshold={threshold}
            setThreshold={setThreshold}
            onStartRun={createCustomerCase}
            onSelectRun={selectRunForWorkspace}
            loading={loading}
          />
        )}

        {/* Page 2: Customer Resolution Workspace */}
        {activeView === "workspace" && (
          <ResolutionWorkspaceView
            currentRun={currentRun}
            onBackToQueue={() => setActiveView("queue")}
            onSubmitApproval={submitApproval}
            onStartExecution={startRunExecution}
            loading={loading}
          />
        )}
      </main>

      {/* LLM Provider Configuration Drawer */}
      <LlmSettingsDrawer
        isOpen={showLlmDrawer}
        onClose={() => setShowLlmDrawer(false)}
        llmConfig={llmConfig}
        onSave={saveLlmConfig}
        onReset={resetLlmConfig}
        saving={llmSaving}
      />
    </div>
  );
}
