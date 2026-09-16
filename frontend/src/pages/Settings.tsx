import { useEffect, useRef, useState } from "react";
import { ResumeApi, SystemApi } from "../api";
import type { AgentMeta, OllamaStatus, ResumeInfo } from "../types";

export default function Settings() {
  const [resumes, setResumes] = useState<ResumeInfo[]>([]);
  const [active, setActive] = useState<ResumeInfo | null>(null);
  const [text, setText] = useState("");
  const [name, setName] = useState("My Capabilities");
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [pulling, setPulling] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function loadAll() {
    const [rs, act] = await Promise.all([ResumeApi.list(), ResumeApi.active()]);
    setResumes(rs);
    setActive(act);
    if (act?.text) setText(act.text);
    SystemApi.ollama().then(setOllama).catch(() => {});
    SystemApi.agents().then(setAgents).catch(() => {});
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function saveText() {
    setBusy(true);
    try {
      await ResumeApi.fromText(name, text);
      await loadAll();
    } finally {
      setBusy(false);
    }
  }

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const r = await ResumeApi.upload(file);
      setText(r.text || "");
      if (fileRef.current) fileRef.current.value = "";
      await loadAll();
    } finally {
      setBusy(false);
    }
  }

  async function activate(id: number) {
    await ResumeApi.update(id, { is_active: true });
    await loadAll();
  }
  async function remove(id: number) {
    if (!confirm("Delete this resume?")) return;
    await ResumeApi.remove(id);
    await loadAll();
  }

  async function pull() {
    setPulling(true);
    try {
      await SystemApi.pull();
      await loadAll();
    } catch (e: any) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setPulling(false);
    }
  }

  return (
    <div>
      <h1>Settings</h1>
      <p className="subtitle">
        Your resume/capabilities drive the fit analysis. Manage the Ollama model and see the agent
        roster here.
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
        <h2 style={{ marginTop: 0 }}>Resume / Capabilities</h2>
        <div className="row" style={{ marginBottom: 10 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
          <input type="file" ref={fileRef} accept=".pdf,.docx,.txt" />
          <button className="ghost" onClick={upload} disabled={busy}>
            Upload (.docx/.pdf)
          </button>
        </div>
        <textarea
          rows={12}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste everything you can do: skills, past performance, degrees, technologies, domains…"
        />
        <div style={{ marginTop: 10 }}>
          <button onClick={saveText} disabled={busy || !text.trim()}>
            Save as active resume
          </button>
          {active && (
            <span className="meta" style={{ marginLeft: 10 }}>
              Active: {active.name} ({active.chars} chars)
            </span>
          )}
        </div>

        {resumes.length > 0 && (
          <table style={{ marginTop: 16 }}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Chars</th>
                <th>Active</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {resumes.map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td>{r.chars}</td>
                  <td>{r.is_active ? <span className="pill green">active</span> : ""}</td>
                  <td>
                    {!r.is_active && (
                      <button className="ghost small" onClick={() => activate(r.id)}>
                        activate
                      </button>
                    )}{" "}
                    <button className="ghost small danger" onClick={() => remove(r.id)}>
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Agent roster</h2>
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
