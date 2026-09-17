import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SystemApi } from "../api";
import type { AgentMeta, OllamaStatus } from "../types";
import { useToast } from "../toast";

export default function Settings() {
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [pulling, setPulling] = useState(false);
  const toast = useToast();

  async function loadAll() {
    SystemApi.ollama().then(setOllama).catch(() => {});
    SystemApi.agents().then(setAgents).catch(() => {});
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function pull() {
    setPulling(true);
    try {
      await SystemApi.pull();
      await loadAll();
      toast("Model pulled");
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Pull failed", "error");
    } finally {
      setPulling(false);
    }
  }

  return (
    <div>
      <h1>Settings</h1>
      <p className="subtitle">
        Local model and the council roster. Your resume lives on{" "}
        <Link to="/profile">Profile</Link>.
      </p>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Ollama</h2>
        {!ollama && <div className="spinner">Checking Ollama…</div>}
        {ollama && (
          <>
            <div className="row spread">
              <div>
                <div className="kv">Endpoint</div>
                <div style={{ fontSize: 13 }}>{ollama.base_url}</div>
              </div>
              <div>
                <div className="kv">Configured model</div>
                <div style={{ fontSize: 13 }}>{ollama.configured_model}</div>
              </div>
              <div>
                <span className={`pill ${ollama.model_ready ? "green" : "yellow"}`}>
                  {ollama.model_ready ? "model ready" : "model not pulled"}
                </span>
              </div>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              {(ollama.available_models || []).map((m) => (
                <span key={m} className="tag">
                  {m}
                </span>
              ))}
            </div>
            {!ollama.model_ready && (
              <div style={{ marginTop: 12 }}>
                <button onClick={pull} disabled={pulling}>
                  {pulling ? "Pulling (this is large, be patient)…" : `Pull ${ollama.configured_model}`}
                </button>
                <span className="meta" style={{ marginLeft: 10 }}>
                  Until then, the fallback model ({ollama.fallback_model}) is used.
                </span>
              </div>
            )}
          </>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Agent roster</h2>
        <p className="meta">
          These run only when you ask — Inbox ranking never calls the council.
        </p>
        <div className="agent-grid">
          {agents.map((a) => (
            <div key={a.name} className="row" style={{ gap: 8 }}>
              <strong>{a.name}</strong>
              <span className="meta">· {a.role}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
