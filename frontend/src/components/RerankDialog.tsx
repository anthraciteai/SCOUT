import { useEffect, useState } from "react";
import { MatchesApi } from "../api";
import type { RerankOptions, ScanBody } from "../api";

/**
 * Modal that lets the user pick which resume + company blend to rank against.
 * Defaults to their own bundle (ME + Anthracite products) since that is what
 * the ranker was using implicitly before.
 */
export default function RerankDialog({
  open,
  onClose,
  onConfirm,
  running,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (body: ScanBody) => void;
  running: boolean;
}) {
  const [opts, setOpts] = useState<RerankOptions | null>(null);
  const [mode, setMode] = useState<"me" | "employee" | "company">("me");
  const [employeeId, setEmployeeId] = useState<string>("");
  const [includeCompany, setIncludeCompany] = useState(true);
  const [forceExtract, setForceExtract] = useState(true);

  useEffect(() => {
    if (!open) return;
    MatchesApi.rerankOptions()
      .then((r) => {
        setOpts(r);
        // Default: rank as you, with company products merged. Matches the
        // implicit behavior we had before this dialog existed.
        setMode("me");
        setIncludeCompany(true);
        if (r.coworkers.length && !employeeId) setEmployeeId(r.coworkers[0].user_id);
      })
      .catch(() => setOpts(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const you = opts?.you;
  const chosenEmployee = opts?.coworkers.find((c) => c.user_id === employeeId);

  const summary = (() => {
    if (mode === "company") {
      return `Rank against ${opts?.company_id || "the company"} mission + products only. No personal resume.`;
    }
    if (mode === "employee") {
      if (!chosenEmployee) return "Pick a coworker to rank as.";
      const parts = [chosenEmployee.display_name];
      if (includeCompany) parts.push("+ company products");
      return `Rank as ${parts.join(" ")} — ${chosenEmployee.me_chars.toLocaleString()} chars of their ME resume.`;
    }
    // "me"
    if (!you) return "Rank against your ME resume.";
    const parts = [`${you.display_name}'s ME (${you.me_chars.toLocaleString()} chars)`];
    if (includeCompany) parts.push(`+ ${opts?.company_id || "company"} products`);
    return `Rank against ${parts.join(" ")}.`;
  })();

  function commit() {
    const body: ScanBody = {
      mode,
      force_extract: forceExtract,
      include_company: mode === "company" ? true : includeCompany,
    };
    if (mode === "employee") body.employee_id = employeeId;
    onConfirm(body);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(4, 8, 16, 0.72)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        backdropFilter: "blur(4px)",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !running) onClose();
      }}
    >
      <div
        className="card"
        style={{
          width: "min(640px, 100%)",
          maxHeight: "90vh",
          overflow: "auto",
          borderColor: "var(--accent)",
          boxShadow: "0 40px 80px -20px rgba(255,122,26,0.35)",
        }}
      >
        <div className="row spread" style={{ alignItems: "baseline" }}>
          <h2 style={{ margin: 0 }}>Re-rank inbox</h2>
          <button className="ghost small" onClick={onClose} disabled={running}>
            close
          </button>
        </div>
        <p className="meta" style={{ margin: "4px 0 14px" }}>
          Ranking walks every open SBIR against your chosen matching pack. Takes several
          minutes and refreshes cached scores.
        </p>

        {!opts ? (
          <div className="meta">Loading options…</div>
        ) : (
          <>
            {/* Mode picker cards */}
            <div style={{ display: "grid", gap: 8 }}>
              <ModeCard
                on={mode === "me"}
                title={`You — ${you?.display_name || "sign in required"}`}
                subtitle={
                  you
                    ? `${you.me_chars.toLocaleString()} chars of ME · Anthracite products merge in by default (recommended)`
                    : "No signed-in user"
                }
                accent="#ff7a1a"
                disabled={!you}
                onClick={() => setMode("me")}
              />
              <ModeCard
                on={mode === "employee"}
                title="A coworker"
                subtitle={
                  opts.coworkers.length
                    ? `Pick someone from ${opts.company_id} — great for "would this SBIR fit Jake's stack?"`
                    : "No other employees on file yet."
                }
                accent="#35d07f"
                disabled={!opts.coworkers.length}
                onClick={() => setMode("employee")}
              />
              <ModeCard
                on={mode === "company"}
                title={`${opts.company_id || "Company"} only`}
                subtitle={`Products + mission only (${opts.company.product_chars.toLocaleString()} + ${opts.company.mission_chars.toLocaleString()} chars). Ignore personal ME.`}
                accent="#8a7bff"
                onClick={() => setMode("company")}
              />
            </div>

            {/* Coworker picker only when mode=employee */}
            {mode === "employee" && (
              <div style={{ marginTop: 12 }}>
                <div className="kv">Rank as</div>
                <select
                  value={employeeId}
                  onChange={(e) => setEmployeeId(e.target.value)}
                  style={{ width: "100%", marginTop: 4 }}
                >
                  {opts.coworkers.map((c) => (
                    <option key={c.user_id} value={c.user_id}>
                      {c.display_name} ({c.user_id}) — {c.me_chars.toLocaleString()} chars
                      {c.has_resume ? "" : " · no resume"}
                    </option>
                  ))}
                </select>
                {chosenEmployee && !chosenEmployee.has_resume && (
                  <p className="meta" style={{ color: "var(--yellow)", marginTop: 6 }}>
                    Heads up: {chosenEmployee.display_name} has no ME resume attached. The
                    ranker will fall back to their skills tags + company products.
                  </p>
                )}
              </div>
            )}

            {/* Company toggle only when mode=me or employee */}
            {mode !== "company" && (
              <label
                style={{
                  marginTop: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={includeCompany}
                  onChange={(e) => setIncludeCompany(e.target.checked)}
                />
                <span>
                  Also blend in <strong>{opts.company_id || "company"}</strong> mission +
                  products
                  <span className="meta" style={{ marginLeft: 6, fontSize: 12 }}>
                    (default on — turn off to score against personal ME only)
                  </span>
                </span>
              </label>
            )}

            <label
              style={{
                marginTop: 8,
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={forceExtract}
                onChange={(e) => setForceExtract(e.target.checked)}
              />
              <span>
                Force LLM re-extract
                <span className="meta" style={{ marginLeft: 6, fontSize: 12 }}>
                  (recommended when the source changes; slower but accurate)
                </span>
              </span>
            </label>

            <div
              style={{
                marginTop: 14,
                padding: 10,
                borderRadius: 6,
                background: "rgba(255,122,26,0.08)",
                borderLeft: "4px solid var(--accent)",
                fontSize: 13,
              }}
            >
              <strong>Confirm:</strong> {summary}
            </div>

            <div className="row" style={{ marginTop: 14, justifyContent: "flex-end", gap: 8 }}>
              <button className="ghost" onClick={onClose} disabled={running}>
                Cancel
              </button>
              <button
                onClick={commit}
                disabled={running || (mode === "employee" && !employeeId)}
                style={{
                  background: "var(--accent)",
                  color: "#0a0b0d",
                  borderColor: "var(--accent)",
                }}
              >
                {running ? "Ranking…" : "Rank now"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ModeCard({
  on,
  title,
  subtitle,
  accent,
  disabled,
  onClick,
}: {
  on: boolean;
  title: string;
  subtitle: string;
  accent: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        textAlign: "left",
        border: `1px solid ${on ? accent : "var(--border)"}`,
        background: on ? `${accent}18` : "transparent",
        padding: "10px 12px",
        borderRadius: 8,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: 999,
            background: on ? accent : "transparent",
            border: `2px solid ${accent}`,
            flexShrink: 0,
          }}
        />
        <strong style={{ fontSize: 14 }}>{title}</strong>
      </div>
      <div className="meta" style={{ fontSize: 12, marginTop: 4, paddingLeft: 18 }}>
        {subtitle}
      </div>
    </button>
  );
}
