import React, { useState } from "react";

interface LlmSettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  llmConfig: {
    provider?: string | null;
    model?: string | null;
    base_url?: string | null;
    is_configured: boolean;
    has_api_key: boolean;
    connection_status: string;
    status_message?: string | null;
  };
  onSave: (payload: { provider: string; model: string; base_url: string; api_key?: string }) => Promise<void>;
  onReset: () => Promise<void>;
  saving: boolean;
}

const DEFAULT_MODELS: Record<string, string> = {
  ollama: "llama3.1",
  groq: "llama-3.3-70b-versatile",
  vllm: "meta-llama/Llama-3.1-8B-Instruct",
  lmstudio: "local-model",
  together: "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
  fireworks: "accounts/fireworks/models/llama-v3p1-70b-instruct",
  custom: "",
};

export const LlmSettingsDrawer: React.FC<LlmSettingsDrawerProps> = ({
  isOpen,
  onClose,
  llmConfig,
  onSave,
  onReset,
  saving,
}) => {
  const [provider, setProvider] = useState<string>(llmConfig.provider || "ollama");
  const [model, setModel] = useState<string>(llmConfig.model || "llama3.1");
  const [baseUrl, setBaseUrl] = useState<string>(llmConfig.base_url || "");
  const [apiKey, setApiKey] = useState<string>("");

  if (!isOpen) return null;

  const handleProviderChange = (prov: string) => {
    setProvider(prov);
    if (DEFAULT_MODELS[prov] !== undefined) {
      setModel(DEFAULT_MODELS[prov]);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSave({
      provider: provider.trim(),
      model: model.trim(),
      base_url: baseUrl.trim(),
      api_key: apiKey.trim() || undefined,
    });
    setApiKey("");
  };

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-container" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="drawer-title-group">
            <h3>LLM Provider Settings</h3>
            <span className="drawer-sub">{llmConfig.status_message}</span>
          </div>
          <button type="button" className="drawer-close" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSave} className="drawer-body">
          <div className="form-group">
            <label className="form-label">Provider Engine</label>
            <select
              className="form-select"
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              <option value="ollama">Ollama (Local)</option>
              <option value="groq">Groq Cloud</option>
              <option value="vllm">vLLM Server</option>
              <option value="lmstudio">LM Studio</option>
              <option value="together">Together AI</option>
              <option value="fireworks">Fireworks AI</option>
              <option value="custom">Custom OpenAI-Compatible Endpoint</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Model Identifier</label>
            <input
              className="form-input"
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. llama-3.3-70b-versatile or llama-3.1-8b-instant"
              required
            />
            <span className="muted font-mono" style={{ fontSize: "0.75rem", marginTop: "0.25rem", display: "block" }}>
              Groq models: llama-3.3-70b-versatile, llama-3.1-8b-instant, llama3-70b-8192
            </span>
          </div>

          <div className="form-group">
            <label className="form-label">Base URL (Optional)</label>
            <input
              className="form-input"
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434/v1"
            />
          </div>

          <div className="form-group">
            <label className="form-label">API Key (Optional / Masked)</label>
            <input
              className="form-input"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={llmConfig.has_api_key ? "•••••••• (Key Configured)" : "Enter API key"}
            />
          </div>

          <div className="drawer-footer">
            <button type="submit" className="btn-enterprise-primary" disabled={saving}>
              {saving ? "Testing & Saving..." : "Save & Verify Connection"}
            </button>
            <button
              type="button"
              className="btn-enterprise-secondary"
              onClick={onReset}
              disabled={saving}
            >
              Reset to Rule-Based Mode
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
