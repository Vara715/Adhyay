import React from "react";

interface HeaderProps {
  activeView: "queue" | "workspace";
  setActiveView: (view: "queue" | "workspace") => void;
  llmConfig: {
    is_configured: boolean;
    provider?: string | null;
    model?: string | null;
    connection_status?: string | null;
  };
  systemHealth: { status: string } | null;
  onOpenLlmSettings: () => void;
  hasActiveRun: boolean;
  isPresentationMode: boolean;
  onTogglePresentationMode: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeView,
  setActiveView,
  llmConfig,
  systemHealth,
  onOpenLlmSettings,
  hasActiveRun,
  isPresentationMode,
  onTogglePresentationMode,
}) => {
  const getLlmStatusDotColor = () => {
    if (llmConfig.connection_status === "error") return "#ef4444";
    if (llmConfig.is_configured && llmConfig.connection_status === "ok") return "#22c55e";
    if (llmConfig.is_configured) return "#3b82f6";
    return "#eab308";
  };

  const getLlmStatusText = () => {
    if (llmConfig.connection_status === "error") return "CONNECTION ERROR";
    if (llmConfig.is_configured) {
      const p = (llmConfig.provider || "LLM").toUpperCase();
      const m = llmConfig.model ? ` (${llmConfig.model})` : "";
      return `CONNECTED — ${p}${m}`;
    }
    return "RULE-BASED FALLBACK";
  };

  return (
    <header className="app-header-bar">
      <div className="header-brand">
        <span className="logo-badge">A</span>
        <div className="header-title-group">
          <h1 className="header-app-name">Adhyay</h1>
          <span className="header-app-sub">AUTONOMOUS CUSTOMER RESOLUTION AGENT (PS5)</span>
        </div>
      </div>

      <nav className="header-nav-tabs">
        <button
          type="button"
          className={`nav-tab ${activeView === "queue" ? "active" : ""}`}
          onClick={() => setActiveView("queue")}
        >
          <span>Customer Case Queue</span>
        </button>
        <button
          type="button"
          className={`nav-tab ${activeView === "workspace" ? "active" : ""}`}
          onClick={() => setActiveView("workspace")}
        >
          <span>Resolution Workspace</span>
          {hasActiveRun && <span className="active-dot" title="Active Case Running" />}
        </button>
      </nav>

      <div className="header-status-group">
        <button
          type="button"
          className={`presentation-toggle-btn ${isPresentationMode ? "active" : ""}`}
          onClick={onTogglePresentationMode}
          title="Toggle wide presentation view for judge demonstrations"
        >
          📺 {isPresentationMode ? "Normal View" : "Presentation View"}
        </button>
        <button
          type="button"
          className="status-pill cursor-pointer"
          onClick={onOpenLlmSettings}
          title="Click to configure LLM provider settings"
        >
          <span
            className="status-dot"
            style={{ backgroundColor: getLlmStatusDotColor() }}
          />
          <span>{getLlmStatusText()}</span>
          <span className="settings-gear-icon">⚙️</span>
        </button>
        <span className="status-pill">
          <span
            className="status-dot"
            style={{ backgroundColor: systemHealth?.status === "healthy" || systemHealth?.status === "ok" ? "#22c55e" : "#ef4444" }}
          />
          <span>Backend: {systemHealth?.status || "Checking..."}</span>
        </span>
      </div>
    </header>
  );
};
