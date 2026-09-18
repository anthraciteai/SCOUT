import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Login() {
  const { status, login } = useAuth();
  const [username, setUsername] = useState("ken");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const noPass = Boolean(status?.auth_disabled);

  async function asUser(uid: string) {
    setBusy(true);
    setErr("");
    try {
      await login(uid, noPass ? "" : password || uid);
      navigate("/org");
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="card"
      style={{
        maxWidth: 520,
        margin: "60px auto",
        padding: 32,
        background: "linear-gradient(180deg, var(--surface), var(--bg-2))",
        boxShadow: "var(--shadow)",
      }}
    >
      <h1>Sign in to SCOUT</h1>
      <p className="subtitle">
        Access is gated by <code>companies/&lt;id&gt;/employees/&lt;you&gt;</code> existing. Ken,
        Jake, and Matt share Anthracite — each keeps a private folder under{" "}
        <code>sbir/&#123;topic&#125;/anthracite/users/&#123;you&#125;</code>.
      </p>
      {noPass && (
        <p className="meta">Stub auth is on (password = username). Pick a person to collaborate.</p>
      )}
      <div className="row" style={{ marginBottom: 14 }}>
        {(status?.users || []).map((u) => (
          <button
            key={u.user_id}
            className="ghost"
            disabled={busy}
            onClick={() => asUser(u.user_id)}
          >
            {u.display_name}
          </button>
        ))}
      </div>
      <div className="row">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="username"
        />
        {!noPass && (
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="password"
          />
        )}
        <button onClick={() => asUser(username)} disabled={busy || !username.trim()}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </div>
      {err && (
        <p style={{ color: "var(--red)", marginTop: 10 }}>{err}</p>
      )}
    </div>
  );
}
