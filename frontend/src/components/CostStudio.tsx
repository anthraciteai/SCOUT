import { useEffect, useMemo, useRef, useState } from "react";
import {
  ProposalsApi,
  streamDynomite,
  type BomCategory,
  type BomLine,
  type CostPhase,
  type CostState,
  type CostRollup,
} from "../api";
import { useToast } from "../toast";

/**
 * Cost Studio for a proposal.
 *
 *   - Dynomite chat (left)  →  builds the BOM turn-by-turn. Every reply ends
 *     with a fenced JSON block; the backend parses it and persists the BOM.
 *   - Live BOM table (right) → editable, adds up subtotals as you type.
 *   - Budget Man rollup (bottom) → applies fringe/OH/G&A/fee, checks phase cap,
 *     and returns a short human summary of the math + warnings.
 */
export default function CostStudio({
  proposalId,
  proposalTitle,
}: {
  proposalId: number;
  proposalTitle: string;
}) {
  const [state, setState] = useState<CostState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [liveTurn, setLiveTurn] = useState("");
  const [rollupBusy, setRollupBusy] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const chatBoxRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const toast = useToast();

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await ProposalsApi.cost(proposalId);
      setState(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Load failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposalId]);

  useEffect(() => {
    // Autoscroll chat as it streams.
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [state?.chat.length, liveTurn]);

  async function send() {
    if (!msg.trim() || streaming) return;
    const outgoing = msg.trim();
    setMsg("");
    setStreaming(true);
    setLiveTurn("");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamDynomite(
        proposalId,
        outgoing,
        (chunk) => setLiveTurn((prev) => prev + chunk),
        ac.signal
      );
      // Server has persisted BOM + chat; refetch canonical state.
      await load();
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setError(e?.message || "Dynomite failed");
      }
    } finally {
      setStreaming(false);
      setLiveTurn("");
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  async function runRollup() {
    setRollupBusy(true);
    try {
      const roll = await ProposalsApi.rollup(proposalId);
      setState((prev) => (prev ? { ...prev, rollup: roll } : prev));
      toast(`Budget Man: $${(roll.total || 0).toLocaleString()}`);
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Rollup failed", "error");
    } finally {
      setRollupBusy(false);
    }
  }

  async function updatePhase(phase: CostPhase) {
    const next = await ProposalsApi.putRates(proposalId, { phase });
    setState(next);
  }

  async function updateRate(key: keyof CostState["rates"], val: number) {
    const next = await ProposalsApi.putRates(proposalId, { [key]: val } as any);
    setState(next);
  }

  async function saveBom(bom: BomLine[]) {
    const next = await ProposalsApi.putBom(proposalId, bom);
    setState(next);
  }

  async function clearChat() {
    if (!confirm("Clear the Dynomite chat history? (BOM is kept.)")) return;
    const next = await ProposalsApi.clearCostChat(proposalId);
    setState(next);
  }

  if (loading) return <div className="card spinner">Loading cost studio…</div>;
  if (!state) return null;

  return (
    <div className="card">
      <div className="row spread">
        <div>
          <h3 style={{ margin: 0 }}>
            Cost studio — <span style={{ color: "var(--ember)" }}>Dynomite</span> ×{" "}
            <span style={{ color: "#8a7bff" }}>Budget Man</span>
          </h3>
          <p className="meta" style={{ margin: "4px 0 0" }}>
            Dynomite is the shop foreman — he chats you through every BOM line.
            Budget Man is the finance guy — he rolls it up with fringe / OH /
            G&amp;A / fee and yells if it's over the phase cap. Proposal:{" "}
            <em>{proposalTitle}</em>.
          </p>
        </div>
        <PhaseSelector value={state.phase} onChange={updatePhase} />
      </div>

      {error && (
        <div style={{ color: "var(--red)", marginTop: 8, fontSize: 13 }}>{error}</div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginTop: 12,
        }}
      >
        {/* --- Chat pane --------------------------------------------------- */}
        <div>
          <div
            ref={chatBoxRef}
            style={{
              height: 340,
              overflowY: "auto",
              background: "var(--panel-2)",
              borderRadius: 6,
              padding: 10,
              fontSize: 13,
              lineHeight: 1.5,
            }}
          >
            {state.chat.length === 0 && !liveTurn && (
              <div className="meta">
                Say hi to Dynomite. Something like:
                <br />
                <em>
                  "Phase I, 6 months. One senior SWE at ~$180/hr for 320 hours,
                  one PI at 20% for the whole phase, and we need a Xavier NX
                  dev kit ($2.5k) and one kickoff trip to Dahlgren."
                </em>
              </div>
            )}
            {state.chat.map((t, i) => (
              <ChatBubble key={i} role={t.role} content={t.content} />
            ))}
            {streaming && liveTurn && (
              <ChatBubble role="assistant" content={liveTurn} />
            )}
            {streaming && !liveTurn && (
              <div className="meta">Dynomite is thinking…</div>
            )}
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <textarea
              className="grow"
              rows={2}
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              placeholder="Ask Dynomite: 'add a subK at $40k for optics polishing'…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
              }}
              disabled={streaming}
            />
            {streaming ? (
              <button className="danger" onClick={stop}>
                Stop
              </button>
            ) : (
              <button onClick={send} disabled={!msg.trim()}>
                Send
              </button>
            )}
          </div>
          <div className="row spread" style={{ marginTop: 4 }}>
            <span className="meta" style={{ fontSize: 11 }}>
              ⌘/Ctrl + Enter to send.
            </span>
            <button
              className="ghost small"
              onClick={clearChat}
              disabled={state.chat.length === 0}
            >
              clear chat
            </button>
          </div>
        </div>

        {/* --- BOM table -------------------------------------------------- */}
        <div>
          <BomTable
            bom={state.bom}
            onChange={saveBom}
            disabled={streaming}
          />
        </div>
      </div>

      {/* --- Rates + Budget Man rollup ------------------------------------ */}
      <div style={{ marginTop: 12, borderTop: "1px solid var(--panel-2)", paddingTop: 12 }}>
        <div className="row spread">
          <div className="row" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button onClick={runRollup} disabled={rollupBusy || state.bom.length === 0}>
              {rollupBusy ? "Budget Man is adding…" : "Ask Budget Man to roll it up"}
            </button>
            <span className="meta" style={{ fontSize: 12 }}>
              Cap: <strong>${(state.phase_cap || 0).toLocaleString()}</strong>{" "}
              ({state.phase_label})
            </span>
            <button
              className="ghost small"
              onClick={() => setShowAdvanced((v) => !v)}
            >
              {showAdvanced ? "hide rates" : "edit rates"}
            </button>
          </div>
          {state.rollup && (
            <RollupBadge rollup={state.rollup} cap={state.phase_cap} />
          )}
        </div>

        {showAdvanced && (
          <div
            className="row"
            style={{
              gap: 12,
              marginTop: 8,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <RateInput
              label="Fringe %"
              value={state.rates.fringe_pct}
              onCommit={(v) => updateRate("fringe_pct", v)}
            />
            <RateInput
              label="Overhead %"
              value={state.rates.overhead_pct}
              onCommit={(v) => updateRate("overhead_pct", v)}
            />
            <RateInput
              label="G&A %"
              value={state.rates.ga_pct}
              onCommit={(v) => updateRate("ga_pct", v)}
            />
            <RateInput
              label="Fee %"
              value={state.rates.fee_pct}
              onCommit={(v) => updateRate("fee_pct", v)}
              max={7}
            />
            <span className="meta" style={{ fontSize: 11 }}>
              DoD SBIR fee is clamped at 7%.
            </span>
          </div>
        )}

        {state.rollup && <RollupCard rollup={state.rollup} cap={state.phase_cap} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat bubble
// ---------------------------------------------------------------------------
function ChatBubble({
  role,
  content,
}: {
  role: "user" | "assistant";
  content: string;
}) {
  // Hide the trailing JSON fence from the user — it's for the backend, not
  // them. Everything before the last ```json block is human-facing.
  const display = useMemo(() => {
    if (role !== "assistant") return content;
    const idx = content.lastIndexOf("```json");
    if (idx > 0) return content.slice(0, idx).trimEnd();
    const fallback = content.lastIndexOf("```");
    if (fallback > 0) return content.slice(0, fallback).trimEnd();
    return content;
  }, [role, content]);
  const isMe = role === "user";
  return (
    <div
      style={{
        margin: "6px 0",
        display: "flex",
        justifyContent: isMe ? "flex-end" : "flex-start",
      }}
    >
      <div
        style={{
          maxWidth: "85%",
          padding: "8px 10px",
          borderRadius: 8,
          background: isMe ? "rgba(138,123,255,0.18)" : "rgba(255,122,26,0.12)",
          border: `1px solid ${isMe ? "rgba(138,123,255,0.4)" : "rgba(255,122,26,0.4)"}`,
          whiteSpace: "pre-wrap",
          fontSize: 13,
        }}
      >
        <div
          className="meta"
          style={{ fontSize: 10.5, marginBottom: 2, textTransform: "uppercase" }}
        >
          {isMe ? "You" : "Dynomite"}
        </div>
        {display || "…"}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BOM table (inline edit)
// ---------------------------------------------------------------------------
const CATEGORY_META: Record<BomCategory, { label: string; color: string }> = {
  labor: { label: "Labor", color: "#ff7a1a" },
  materials: { label: "Materials", color: "#5aa9ff" },
  equipment: { label: "Equipment", color: "#8a7bff" },
  travel: { label: "Travel", color: "#35d07f" },
  subcontract: { label: "Subcontract", color: "#e6c07b" },
  odc: { label: "ODC", color: "#a0a0a0" },
};

function BomTable({
  bom,
  onChange,
  disabled,
}: {
  bom: BomLine[];
  onChange: (bom: BomLine[]) => void;
  disabled?: boolean;
}) {
  const [local, setLocal] = useState<BomLine[]>(bom);
  useEffect(() => setLocal(bom), [bom]);

  function commit(next: BomLine[]) {
    setLocal(next);
    onChange(next);
  }

  function updateLine(i: number, patch: Partial<BomLine>) {
    const next = local.map((ln, idx) => (idx === i ? { ...ln, ...patch } : ln));
    setLocal(next);
  }

  function addBlank() {
    const nextId = `L${local.length + 1}`;
    commit([
      ...local,
      { id: nextId, category: "labor", name: "", qty: 0, unit: "hours", unit_cost: 0 },
    ]);
  }

  function removeLine(i: number) {
    commit(local.filter((_, idx) => idx !== i));
  }

  const total = local.reduce((s, ln) => s + (ln.qty || 0) * (ln.unit_cost || 0), 0);

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 6 }}>
        <strong style={{ fontSize: 13 }}>BOM ({local.length})</strong>
        <span className="meta" style={{ fontSize: 12 }}>
          Direct subtotal <strong>${total.toLocaleString()}</strong>
        </span>
      </div>
      <div
        style={{
          background: "var(--panel-2)",
          borderRadius: 6,
          maxHeight: 340,
          overflowY: "auto",
        }}
      >
        {local.length === 0 && (
          <div className="meta" style={{ padding: 12 }}>
            No lines yet. Chat with Dynomite or add one manually.
          </div>
        )}
        {local.map((ln, i) => (
          <div
            key={ln.id || i}
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr 60px 60px 90px 32px",
              gap: 6,
              alignItems: "center",
              padding: "6px 8px",
              borderBottom: "1px solid rgba(255,255,255,0.05)",
              fontSize: 12,
            }}
          >
            <select
              value={ln.category}
              onChange={(e) =>
                updateLine(i, { category: e.target.value as BomCategory })
              }
              onBlur={() => commit(local)}
              disabled={disabled}
              style={{
                background: `${CATEGORY_META[ln.category].color}20`,
                color: CATEGORY_META[ln.category].color,
                fontWeight: 700,
                fontSize: 11,
              }}
            >
              {(Object.keys(CATEGORY_META) as BomCategory[]).map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_META[c].label}
                </option>
              ))}
            </select>
            <input
              value={ln.name}
              onChange={(e) => updateLine(i, { name: e.target.value })}
              onBlur={() => commit(local)}
              placeholder="Line item"
              disabled={disabled}
            />
            <input
              type="number"
              min={0}
              step="any"
              value={ln.qty}
              onChange={(e) => updateLine(i, { qty: Number(e.target.value) })}
              onBlur={() => commit(local)}
              disabled={disabled}
              title="qty"
            />
            <input
              value={ln.unit}
              onChange={(e) => updateLine(i, { unit: e.target.value })}
              onBlur={() => commit(local)}
              disabled={disabled}
              title="unit"
            />
            <input
              type="number"
              min={0}
              step="any"
              value={ln.unit_cost}
              onChange={(e) =>
                updateLine(i, { unit_cost: Number(e.target.value) })
              }
              onBlur={() => commit(local)}
              disabled={disabled}
              title="unit cost ($)"
            />
            <button
              className="ghost small danger"
              onClick={() => removeLine(i)}
              disabled={disabled}
              title="remove"
            >
              ×
            </button>
            {ln.notes && (
              <div
                className="meta"
                style={{
                  gridColumn: "2 / -1",
                  fontSize: 11,
                  marginTop: -2,
                  marginBottom: 2,
                }}
                title={ln.notes}
              >
                {ln.notes}
              </div>
            )}
          </div>
        ))}
      </div>
      <button
        className="ghost small"
        onClick={addBlank}
        disabled={disabled}
        style={{ marginTop: 6 }}
      >
        + line
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase selector
// ---------------------------------------------------------------------------
function PhaseSelector({
  value,
  onChange,
}: {
  value: CostPhase;
  onChange: (v: CostPhase) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as CostPhase)}
      style={{ fontWeight: 700 }}
    >
      <option value="phase1">Phase I</option>
      <option value="phase2">Phase II</option>
      <option value="direct_to_phase2">Direct to Phase II</option>
    </select>
  );
}

// ---------------------------------------------------------------------------
// Rate input
// ---------------------------------------------------------------------------
function RateInput({
  label,
  value,
  onCommit,
  max,
}: {
  label: string;
  value: number;
  onCommit: (v: number) => void;
  max?: number;
}) {
  const [v, setV] = useState<string>(String(value));
  useEffect(() => setV(String(value)), [value]);
  return (
    <label className="meta" style={{ fontSize: 12 }}>
      {label}{" "}
      <input
        type="number"
        min={0}
        max={max}
        step="0.5"
        value={v}
        style={{ width: 66 }}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => {
          const n = Number(v);
          if (!Number.isNaN(n) && n !== value) onCommit(n);
        }}
      />
    </label>
  );
}

// ---------------------------------------------------------------------------
// Rollup output
// ---------------------------------------------------------------------------
function RollupBadge({
  rollup,
  cap,
}: {
  rollup: CostRollup;
  cap: number | null;
}) {
  const over = cap != null && rollup.total > cap;
  return (
    <div style={{ textAlign: "right" }}>
      <div
        style={{
          fontSize: 22,
          fontWeight: 800,
          color: over ? "var(--red)" : "var(--green)",
        }}
      >
        ${Math.round(rollup.total).toLocaleString()}
      </div>
      {cap != null && (
        <div className="meta" style={{ fontSize: 11 }}>
          {over ? "over" : "under"} cap by $
          {Math.abs(Math.round(rollup.headroom || 0)).toLocaleString()}
        </div>
      )}
    </div>
  );
}

function RollupCard({
  rollup,
  cap,
}: {
  rollup: CostRollup;
  cap: number | null;
}) {
  const rows: [string, number][] = [
    ["Direct labor", rollup.labor],
    ["Fringe", rollup.fringe],
    ["Overhead", rollup.overhead],
    ["Non-labor direct", rollup.direct_non_labor],
    ["G&A", rollup.g_and_a],
    ["Fee", rollup.fee],
  ];
  const over = cap != null && rollup.total > cap;
  return (
    <div
      className="card"
      style={{
        marginTop: 10,
        borderColor: over ? "var(--red)" : "var(--panel-2)",
        background: "var(--panel-2)",
        padding: 12,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
        }}
      >
        <div>
          <strong style={{ fontSize: 13 }}>Budget Man rollup</strong>
          <table
            style={{
              width: "100%",
              fontSize: 12,
              marginTop: 6,
              borderCollapse: "collapse",
            }}
          >
            <tbody>
              {rows.map(([k, v]) => (
                <tr key={k}>
                  <td style={{ padding: "2px 4px", color: "var(--muted)" }}>
                    {k}
                  </td>
                  <td style={{ padding: "2px 4px", textAlign: "right" }}>
                    ${Math.round(v).toLocaleString()}
                  </td>
                </tr>
              ))}
              <tr
                style={{
                  borderTop: "1px solid rgba(255,255,255,0.08)",
                  fontWeight: 700,
                }}
              >
                <td style={{ padding: "4px" }}>Total</td>
                <td
                  style={{
                    padding: "4px",
                    textAlign: "right",
                    color: over ? "var(--red)" : "var(--green)",
                  }}
                >
                  ${Math.round(rollup.total).toLocaleString()}
                </td>
              </tr>
              {cap != null && (
                <tr>
                  <td style={{ padding: "2px 4px", color: "var(--muted)" }}>
                    Phase cap
                  </td>
                  <td style={{ padding: "2px 4px", textAlign: "right" }}>
                    ${cap.toLocaleString()}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {rollup.warnings && rollup.warnings.length > 0 && (
            <ul
              style={{
                marginTop: 8,
                marginBottom: 0,
                paddingLeft: 18,
                color: "var(--amber)",
                fontSize: 12,
              }}
            >
              {rollup.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <strong style={{ fontSize: 13 }}>Budget Man says</strong>
          <div
            style={{
              marginTop: 6,
              fontSize: 13,
              whiteSpace: "pre-wrap",
              lineHeight: 1.5,
            }}
          >
            {rollup.narrative || "(no narrative)"}
          </div>
        </div>
      </div>
    </div>
  );
}
