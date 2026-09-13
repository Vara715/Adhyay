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
}

export const Header: React.FC<HeaderProps> = ({
  activeView,
  setActiveView,
  llmConfig,
  systemHealth,
  onOpenLlmSettings,
  hasActiveRun,
}) => {
  const getLlmStatusDotColor = () => {
    if (llmConfig.connection_status === "error") return "#ef4444";
    if (llmConfig.is_configured) return "#22c55e";
    return "#eab308";
  };

  const getLlmStatusText = () => {
    if (llmConfig.connection_status === "error") return `LLM: Error (Fallback)`;
    if (llmConfig.is_configured) return `LLM: ${llmConfig.provider}/${llmConfig.model}`;
    return "LLM: Rule-Based Mode";
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
