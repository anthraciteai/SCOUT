import { useEffect, useMemo, useRef, useState } from "react";
import {
  ProposalsApi,
  streamPersonaReview,
  type PersonaMeta,
  type ProposalReview,
  type ReviewPersona,
} from "../api";
import { useToast } from "../toast";

// One color per persona so past reviews are visually scannable in the list.
const PERSONA_COLORS: Record<ReviewPersona, string> = {
  technical: "#ff7a1a", // ember — engineering
  military: "#a3a9b4", // steel — mission / BD
  researcher: "#35d07f", // green — academic rigor
};

const PERSONA_ORDER: ReviewPersona[] = ["technical", "military", "researcher"];

function parseScore(body: string): number | null {
  // Personas end with a line "SCORE: <0-100>". Grab the last one so a mid-stream
  // "score" mention doesn't fool the parser.
  const matches = [...(body || "").matchAll(/^\s*SCORE:\s*(\d{1,3})/gim)];
  if (!matches.length) return null;
  const raw = Number(matches[matches.length - 1][1]);
  if (!Number.isFinite(raw)) return null;
  return Math.max(0, Math.min(100, raw));
}

function scoreColor(n: number | null): string {
  if (n == null) return "#3a3a44";
  if (n >= 75) return "#ff7a1a";
  if (n >= 60) return "#35d07f";
  if (n >= 40) return "#8a7bff";
  return "#3a3a44";
}

function timeAgo(iso: string): string {
  const d = new Date(iso);
  const secs = (Date.now() - d.getTime()) / 1000;
  if (secs < 60) return `${Math.round(secs)}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return d.toLocaleDateString();
}

export default function PastReviews({
  proposalId,
  currentSha,
  proposalChars,
}: {
  proposalId: number;
  /** sha of the currently loaded proposal text, so we can flag drift on old reviews */
  currentSha?: string;
  proposalChars?: number;
}) {
  const [personas, setPersonas] = useState<PersonaMeta[]>([]);
  const [tab, setTab] = useState<ReviewPersona>("technical");
  const [reviews, setReviews] = useState<Record<ReviewPersona, ProposalReview[]>>({
    technical: [],
    military: [],
    researcher: [],
  });
  const [openId, setOpenId] = useState<number | "live" | null>(null);
  const [live, setLive] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const toast = useToast();

  async function loadAll() {
    const [personasResp, tech, mil, res] = await Promise.all([
      ProposalsApi.personas().catch(() => []),
      ProposalsApi.reviews(proposalId, "technical").catch(() => []),
      ProposalsApi.reviews(proposalId, "military").catch(() => []),
      ProposalsApi.reviews(proposalId, "researcher").catch(() => []),
    ]);
    setPersonas(personasResp);
    setReviews({ technical: tech, military: mil, researcher: res });
    // Preselect the latest review in this tab.
    const seed = tech[0] || mil[0] || res[0];
    if (seed) setOpenId((prev) => prev ?? seed.id);
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposalId]);

  const currentPersona = useMemo(
    () => personas.find((p) => p.key === tab) || null,
    [personas, tab]
  );
  const list = reviews[tab] || [];
  const openReview = openId && openId !== "live" ? list.find((r) => r.id === openId) : null;

  async function runReview() {
    setStreaming(true);
    setLive("");
    setOpenId("live");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamPersonaReview(
        proposalId,
        tab,
        (chunk) => setLive((prev) => prev + chunk),
        ac.signal
      );
      // Server persisted the row — reload and select it.
      const fresh = await ProposalsApi.reviews(proposalId, tab);
      setReviews((r) => ({ ...r, [tab]: fresh }));
      if (fresh[0]) setOpenId(fresh[0].id);
      setLive("");
    } catch (e: any) {
      if (e.name !== "AbortError") {
        toast(e.message || "Review failed", "error");
      }
    } finally {
      setStreaming(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  async function deleteReview(rid: number) {
    if (!confirm("Delete this saved review?")) return;
    await ProposalsApi.deleteReview(rid);
    const fresh = await ProposalsApi.reviews(proposalId, tab);
    setReviews((r) => ({ ...r, [tab]: fresh }));
    if (openId === rid) setOpenId(fresh[0]?.id ?? null);
  }

  const bodyToShow = openId === "live" ? live : openReview?.body || "";
  const scoreShown = parseScore(bodyToShow);

  return (
    <div className="card">
      <div className="row spread" style={{ alignItems: "flex-start", gap: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>Past reviews</h3>
          <div className="meta">
            Three named voices review this proposal and every run is saved so you can
            revisit later. Great for iterating between passes.
          </div>
        </div>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {PERSONA_ORDER.map((key) => {
            const meta = personas.find((p) => p.key === key);
            const label = meta?.label || key;
            const count = reviews[key]?.length || 0;
            const on = tab === key;
            const color = PERSONA_COLORS[key];
            return (
              <button
                key={key}
                className={on ? "small" : "ghost small"}
                onClick={() => {
                  setTab(key);
                  setOpenId(reviews[key]?.[0]?.id ?? null);
                  setLive("");
                }}
                style={
                  on
                    ? { background: color, color: "#0a0b0d", borderColor: color }
                    : { borderColor: color, color }
                }
                title={meta?.blurb}
              >
                {label} · {count}
              </button>
            );
          })}
        </div>
      </div>

      {currentPersona && (
        <p className="meta" style={{ margin: "10px 0 6px" }}>
          <span style={{ color: PERSONA_COLORS[tab], fontWeight: 600 }}>
            {currentPersona.label}
          </span>
          {" — "}
          {currentPersona.blurb}
        </p>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "220px 1fr",
          gap: 12,
          marginTop: 10,
        }}
      >
        {/* Left: list of past runs for this persona */}
        <div>
          <button
            className="small"
            style={{
              width: "100%",
              marginBottom: 8,
              background: PERSONA_COLORS[tab],
              color: "#0a0b0d",
              borderColor: PERSONA_COLORS[tab],
            }}
            onClick={runReview}
            disabled={streaming}
          >
            {streaming ? "Reviewing…" : `Run ${currentPersona?.label || tab} review`}
          </button>
          {streaming && (
            <button className="ghost small danger" style={{ width: "100%" }} onClick={stop}>
              Stop
            </button>
          )}
          {list.length === 0 && !streaming && (
            <div className="meta" style={{ fontSize: 12 }}>
              No {tab} reviews saved yet. Run one — the snapshot is kept forever.
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {list.map((r) => {
              const score = parseScore(r.body);
              const active = openId === r.id;
              const drift = currentSha && r.proposal_sha && currentSha !== r.proposal_sha;
              return (
                <div
                  key={r.id}
                  onClick={() => {
                    setOpenId(r.id);
                    setLive("");
                  }}
                  style={{
                    cursor: "pointer",
                    padding: "8px 10px",
                    borderRadius: 6,
                    border: `1px solid ${active ? PERSONA_COLORS[tab] : "var(--border)"}`,
                    background: active ? "rgba(255,255,255,0.03)" : "transparent",
                  }}
                  title={`${r.proposal_chars} chars${drift ? " · proposal has changed since this review" : ""}`}
                >
                  <div className="row spread" style={{ gap: 6 }}>
                    <strong style={{ fontSize: 12 }}>{timeAgo(r.created_at)}</strong>
                    <span
                      style={{
                        fontSize: 11,
                        color: scoreColor(score),
                        fontWeight: 700,
                      }}
                    >
                      {score != null ? `${score}` : "—"}
                    </span>
                  </div>
                  <div className="meta" style={{ fontSize: 11, marginTop: 2 }}>
                    {r.proposal_chars} chars
                    {drift ? " · drifted" : ""}
                    {r.model ? ` · ${r.model}` : ""}
                  </div>
                  <button
                    className="ghost small danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteReview(r.id);
                    }}
                    style={{ marginTop: 4, fontSize: 10, padding: "2px 6px" }}
                  >
                    delete
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: the selected review body */}
        <div>
          {openId === "live" && !bodyToShow && (
            <div className="meta">Streaming {currentPersona?.label} review…</div>
          )}
          {bodyToShow ? (
            <div>
              {scoreShown != null && (
                <div
                  className="row spread"
                  style={{
                    marginBottom: 8,
                    padding: "8px 12px",
                    borderRadius: 6,
                    background: `${scoreColor(scoreShown)}18`,
                    borderLeft: `4px solid ${scoreColor(scoreShown)}`,
                  }}
                >
                  <strong>
                    {currentPersona?.label} score{" "}
                    <span style={{ color: scoreColor(scoreShown) }}>{scoreShown}</span> / 100
                  </strong>
                  <span className="meta" style={{ fontSize: 12 }}>
                    {openId === "live" ? "live" : timeAgo((openReview as ProposalReview).created_at)}
                  </span>
                </div>
              )}
              <pre
                className="stream"
                style={{
                  whiteSpace: "pre-wrap",
                  fontSize: 13,
                  lineHeight: 1.5,
                  maxHeight: 560,
                  overflow: "auto",
                }}
              >
                {bodyToShow}
              </pre>
            </div>
          ) : (
            !streaming && (
              <div className="meta" style={{ padding: 12 }}>
                Pick a past review on the left, or run a new {currentPersona?.label} review.
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
