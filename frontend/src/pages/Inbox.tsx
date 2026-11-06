import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnalysisApi, CatalogApi, MatchesApi, OrgApi, ResumeApi, TopicIntelApi, TrackerApi } from "../api";
import type { AnalysisRun, MatchInbox, MatchItem, ResumeInfo, SbirWorkspace } from "../types";
import { useToast } from "../toast";
import { topicMeta, statusClass, TopicDates } from "./Browse";
import { CouncilCard } from "./Analysis";
import FlintCard, { type FlintResult } from "../components/FlintCard";
import AgentChat from "../components/AgentChat";
import MatchBreakdown, { bucketFor } from "../components/MatchBreakdown";
import RerankDialog from "../components/RerankDialog";
import WhyMatched from "../components/WhyMatched";
import TopicScatter from "../components/TopicScatter";
import { buildTopicPoints } from "../lib/opportunity";
import type { ScanBody } from "../api";

function scoreClass(n: number) {
  // Align the per-row score chip with the pie buckets so the eye can jump
  // from the top-of-inbox pie right down to the rows and see the same colors.
  const key = bucketFor(n).key;
  if (key === "strong") return "green";
  if (key === "good") return "green";
  if (key === "ok") return "yellow";
  return "muted";
}

function recClass(rec?: string) {
  const v = (rec || "").toUpperCase();
  if (v === "GO" || v === "LEAN GO") return "green";
  if (v === "LEAN NO-GO") return "yellow";
  if (v === "NO-GO") return "red";
  return "muted";
}

export default function Inbox() {
  const [inbox, setInbox] = useState<MatchInbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [deepRunning, setDeepRunning] = useState(false);
  const [deepProgress, setDeepProgress] = useState("");
  const [deepRuns, setDeepRuns] = useState<AnalysisRun[]>([]);
  const [history, setHistory] = useState<AnalysisRun[]>([]);
  const [uploading, setUploading] = useState(false);
  const [me, setMe] = useState<ResumeInfo | null>(null);
  const [flintByTopic, setFlintByTopic] = useState<Record<string, FlintResult>>({});
  const [flintBusy, setFlintBusy] = useState<string | null>(null);
  const [vaultIndex, setVaultIndex] = useState<Record<string, SbirWorkspace>>({});
  const [catalogStatus, setCatalogStatus] = useState<{
    topics_cached?: number;
    topics_enriched?: number;
    topics_tagged?: number;
    enrich_running?: boolean;
  } | null>(null);
  const [rerankOpen, setRerankOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const meFileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const navigate = useNavigate();
  const autoScanStarted = useRef(false);

  async function load(autoScan = false) {
    setError("");
    try {
      const data = await MatchesApi.list();
      setInbox(data);
      if (autoScan && data.resume && !data.scanned_at && !autoScanStarted.current) {
        autoScanStarted.current = true;
        await scan(false, false);
        return;
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Could not load inbox");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(true);
    AnalysisApi.list().then(setHistory).catch(() => {});
    ResumeApi.me().then(setMe).catch(() => {});
    OrgApi.sbirs()
      .then((rows) => setVaultIndex(Object.fromEntries(rows.map((s) => [s.topic_id, s]))))
      .catch(() => {});
    const tick = () =>
      CatalogApi.status()
        .then(setCatalogStatus)
        .catch(() => {});
    tick();
    const id = window.setInterval(tick, 8000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function scan(forceExtract: boolean, warn = true) {
    // First-run auto-scan (warn=false) skips the dialog. All other rerank
    // buttons open the picker so the user can choose ME vs coworker vs company.
    if (warn) {
      setRerankOpen(true);
      return;
    }
    void runScan({ force_extract: forceExtract });
  }

  async function runScan(body: ScanBody) {
    setScanning(true);
    setError("");
    try {
      const data = await MatchesApi.scan(body);
      setInbox(data);
      const src = (data as any)?.profile?._source_breakdown?.source;
      toast(
        `Ranked ${data.matches.length} open topic${data.matches.length === 1 ? "" : "s"}${
          src ? ` · source: ${src}` : ""
        }`
      );
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Scan failed");
    } finally {
      setScanning(false);
      setRerankOpen(false);
    }
  }

  async function uploadResume() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await ResumeApi.upload(file, "ME", "me");
      if (fileRef.current) fileRef.current.value = "";
      toast("Saved as ME. Rankings stay cached until you re-rank.");
      ResumeApi.me().then(setMe).catch(() => {});
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Upload failed", "error");
    } finally {
      setUploading(false);
      setLoading(false);
    }
  }

  async function track(m: MatchItem) {
    await TrackerApi.track({
      topic_id: m.topic_id,
      topic_code: m.topic_code,
      title: m.title,
      component: m.component,
      program: m.program,
      topic_status: m.topic_status,
      raw: m.topic,
    });
    toast(`Added ${m.topic_code || m.topic_id} to pipeline — Group desk is for that bid`);
  }

  async function uploadMe() {
    const file = meFileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await ResumeApi.upload(file, "ME", "me");
      if (meFileRef.current) meFileRef.current.value = "";
      const mine = await ResumeApi.me();
      setMe(mine);
      toast("This is you. Flint will only spark from tools on that resume.");
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Upload failed", "error");
    } finally {
      setUploading(false);
    }
  }

  async function flintOne(m: MatchItem) {
    if (!me) {
      toast("Upload a resume marked ME first — Flint will not invent a toolbox", "error");
      navigate("/profile");
      return;
    }
    setFlintBusy(m.topic_id);
    try {
      const meta = m.topic ? { [m.topic_id]: topicMeta(m.topic) } : undefined;
      const resp = await AnalysisApi.runAgent(m.topic_id, "Flint", meta);
      setFlintByTopic((prev) => ({ ...prev, [m.topic_id]: resp.result as FlintResult }));
      if (resp.cached) toast("Flint served from cache");
      OrgApi.sbirs()
        .then((rows) => setVaultIndex(Object.fromEntries(rows.map((s) => [s.topic_id, s]))))
        .catch(() => {});
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Flint failed", "error");
    } finally {
      setFlintBusy(null);
    }
  }

  async function councilOne(m: MatchItem) {
    setDeepRunning(true);
    setDeepProgress(`Running council on ${m.topic_code || m.title}… this can take several minutes.`);
    try {
      const meta = m.topic ? { [m.topic_id]: topicMeta(m.topic) } : undefined;
      const runs = await AnalysisApi.run([m.topic_id], meta);
      setDeepRuns((prev) => [...runs, ...prev]);
      AnalysisApi.list().then(setHistory).catch(() => {});
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Council failed", "error");
    } finally {
      setDeepRunning(false);
      setDeepProgress("");
    }
  }

  async function deepScoreTop(n = 5) {
    const top = (inbox?.matches || []).slice(0, n);
    if (top.length === 0) return;
    const ok = window.confirm(
      `Deep-score runs the full agent council on the top ${top.length} matches, one at a time. Each topic can take several minutes. The inbox ranking already stands on its own — this is optional.`
    );
    if (!ok) return;
    setDeepRunning(true);
    setDeepRuns([]);
    try {
      for (let i = 0; i < top.length; i++) {
        const m = top[i];
        setDeepProgress(
          `Deep-score ${i + 1}/${top.length}: ${m.topic_code || ""} ${m.title || ""}`
        );
        const meta = m.topic ? { [m.topic_id]: topicMeta(m.topic) } : undefined;
        const runs = await AnalysisApi.run([m.topic_id], meta);
        setDeepRuns((prev) => [...prev, ...runs]);
      }
      AnalysisApi.list().then(setHistory).catch(() => {});
      toast(`Council finished on ${top.length} topic${top.length === 1 ? "" : "s"}`);
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Deep-score failed", "error");
    } finally {
      setDeepRunning(false);
      setDeepProgress("");
    }
  }

  const latestByTopic = new Map<string, AnalysisRun>();
  for (const h of history) {
    if (!latestByTopic.has(h.topic_id)) latestByTopic.set(h.topic_id, h);
  }

  if (loading && !inbox) {
    return <div className="spinner">Loading inbox…</div>;
  }

  const hasResume = Boolean(inbox?.resume && inbox.resume.chars > 0);
  const matches = inbox?.matches || [];
  const scatterPoints = buildTopicPoints(
    matches,
    new Map(
      Array.from(latestByTopic, ([k, v]) => [
        k,
        { fit_score: v.fit_score, recommendation: v.recommendation },
      ])
    )
  );

  // Mark topics you've already scored a personal fit on (gold ring on the map).
  // Pure read of the vault — no model calls.
  const [scoredIds, setScoredIds] = useState<Set<string>>(new Set());
  const scatterIdsKey = scatterPoints.map((p) => p.topicId).join(",");
  useEffect(() => {
    const ids = scatterIdsKey ? scatterIdsKey.split(",") : [];
    if (!ids.length) {
      setScoredIds(new Set());
      return;
    }
    let alive = true;
    TopicIntelApi.fitStatus(ids)
      .then((scored) => {
        if (alive) setScoredIds(new Set(scored));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [scatterIdsKey]);

  if (!hasResume) {
    return (
      <div>
        <h1>Inbox</h1>
        <p className="subtitle">Drop your resume. This is you. Qualified work comes to you.</p>
        <div className="card" style={{ borderColor: "var(--accent)" }}>
          <h2 style={{ marginTop: 0 }}>This is ME</h2>
          <p className="meta" style={{ marginBottom: 12 }}>
            Upload <em>your</em> resume — jobs, languages, platforms, hardware. Flint (the
            creative agent) will only invent approaches from tools that are actually on the
            page. Matching stays local.
          </p>
          <div className="row">
            <input type="file" ref={fileRef} accept=".pdf,.docx,.txt" />
            <button onClick={uploadResume} disabled={uploading}>
              {uploading ? "Uploading…" : "Upload as ME"}
            </button>
            <button className="ghost" onClick={() => navigate("/profile")}>
              Paste instead
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <RerankDialog
        open={rerankOpen}
        onClose={() => setRerankOpen(false)}
        onConfirm={(body) => runScan(body)}
        running={scanning}
      />
      <h1>Inbox</h1>
      <p className="subtitle">
        Ranked for you
        {inbox?.scanned_at && (
          <>
            {" "}· updated{" "}
            {new Date(inbox.scanned_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
          </>
        )}
      </p>

      {error && (
        <div className="card" style={{ color: "var(--red)" }}>
          {error}
        </div>
      )}

      <MatchBreakdown matches={matches} />

      {scatterPoints.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Opportunity map</h3>
          <p className="meta" style={{ marginTop: 0 }}>
            Inbox match (x) vs Council fit (y). Bigger dot = more matched signals; color = component; gold ring = you've scored fit.
          </p>
          <TopicScatter points={scatterPoints} scoredIds={scoredIds} />
        </div>
      )}

      {!me && (
        <div className="card" style={{ borderColor: "#e6c07b" }}>
          <div className="row spread">
            <div className="grow">
              <strong>Flint needs YOU.</strong>
              <p className="meta" style={{ margin: "6px 0 0" }}>
                The company pack ranks topics. Flint — the creative agent — only sparks from
                tools on a resume marked ME. It will not invent a stack.
              </p>
            </div>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <input type="file" ref={meFileRef} accept=".pdf,.docx,.txt" />
            <button onClick={uploadMe} disabled={uploading}>
              {uploading ? "Uploading…" : "Upload as ME"}
            </button>
            <button className="ghost" onClick={() => navigate("/profile")}>
              Paste on Profile
            </button>
          </div>
        </div>
      )}

      {me && (
        <div className="meta" style={{ marginBottom: 10 }}>
          ME: <strong>{me.name}</strong> ({me.chars} chars) — Flint uses this toolbox.{" "}
          <Link to="/profile">edit</Link>
        </div>
      )}

      <div className="card">
        <div className="row spread">
          <div className="grow">
            {inbox?.profile?.summary && (
              <p style={{ fontSize: 14, margin: "0 0 8px" }}>{inbox.profile.summary}</p>
            )}
            <div className="row" style={{ gap: 6 }}>
              {(inbox?.profile?.skills || inbox?.queries || []).slice(0, 12).map((k) => (
                <span className="tag" key={k}>
                  {k}
                </span>
              ))}
            </div>
          </div>
          <div className="row">
            <button className="ghost" onClick={() => scan(true)} disabled={scanning || deepRunning}>
              {scanning ? "Re-ranking…" : "Re-rank from resume"}
            </button>
            <button
              className="ghost"
              onClick={() => deepScoreTop(5)}
              disabled={deepRunning || scanning || matches.length === 0}
              title="Optional. Runs the full council on the top 5 ranked matches. Not automatic."
            >
              Deep-score top {Math.min(5, matches.length) || 5}
            </button>
          </div>
        </div>
        <p className="meta" style={{ margin: "10px 0 0" }}>
          <strong>Scan</strong> ranks every open topic and writes{" "}
          <code>sbirs/&lt;sbir_id&gt;/tags.json</code> for each. Phrase enrich then
          walks the full window (objective + description via Ollama) — that takes a
          while; existence of the file is the gate.
          {catalogStatus && (
            <>
              {" "}
              Tags: {catalogStatus.topics_enriched ?? 0}/{catalogStatus.topics_cached ?? 0} LLM ·{" "}
              {catalogStatus.topics_tagged ?? 0} on-disk in{" "}
              <code>sbirs/&lt;id&gt;/tags.json</code>
              {catalogStatus.enrich_running ? " · running…" : ""}.
            </>
          )}
          {inbox?.catalog && (
            <>
              {" "}
              Last index: {inbox.catalog.listed ?? "—"} listed.
            </>
          )}
          {catalogStatus &&
            !catalogStatus.enrich_running &&
            (catalogStatus.topics_enriched ?? 0) <
              (catalogStatus.topics_cached ?? 0) && (
              <>
                {" "}
                <button
                  className="ghost small"
                  onClick={async () => {
                    await CatalogApi.enrichStart();
                    toast("SBIR tag enrich kicked");
                  }}
                >
                  Restart tag pass
                </button>
              </>
            )}
        </p>
      </div>

      {(scanning || loading) && (
        <div className="card spinner">Scanning open topics against your profile…</div>
      )}
      {deepProgress && <div className="card spinner">{deepProgress}</div>}

      {inbox?.new_since && (inbox?.new_topic_ids?.length ?? 0) > 0 && (
        <div className="meta" style={{ margin: "10px 2px 4px" }}>
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: 999,
              background: "var(--red)",
              marginRight: 6,
              verticalAlign: "middle",
            }}
          />
          {inbox.new_topic_ids?.length} new since{" "}
          {new Date(inbox.new_since).toLocaleString(undefined, {
            weekday: "short",
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })}
        </div>
      )}

      {matches.map((m) => {
        const prior = latestByTopic.get(m.topic_id);
        const t = m.topic;
        return (
          <div
            className="card"
            key={m.topic_id}
            style={m.is_new ? { boxShadow: "inset 3px 0 0 var(--red)" } : undefined}
          >
            <div className="row spread">
              <div className="grow">
                <div className="row" style={{ alignItems: "center", gap: 8 }}>
                  <Link to={`/work/${m.topic_id}`} state={{ topic: t }} className="topic-title">
                    {m.topic_code} — {m.title}
                  </Link>
                  {m.is_new && (
                    <span
                      className="pill red"
                      title={
                        inbox?.new_since
                          ? `Wasn't in the top 50 of the ${new Date(
                              inbox.new_since
                            ).toLocaleString()} scan`
                          : "New in this scan"
                      }
                    >
                      NEW
                    </span>
                  )}
                </div>
                <div className="meta" style={{ marginTop: 4 }}>
                  {m.component} · {m.program}
                </div>
                {t && (
                  <div style={{ marginTop: 6 }}>
                    <TopicDates t={t} />
                  </div>
                )}
                <div className="row" style={{ marginTop: 8, gap: 6, flexWrap: "wrap" }}>
                  {(m.phrases || []).slice(0, 8).map((p) => (
                    <span className="tag" key={p}>
                      {p}
                    </span>
                  ))}
                  {m.reasons.slice(0, 4).map((r) => (
                    <span className="tag" key={r}>
                      {r}
                    </span>
                  ))}
                </div>
              </div>
              <div style={{ textAlign: "right", minWidth: 88 }}>
                <div className={`score ${scoreClass(m.score)}`} style={{ fontSize: 22 }}>
                  {Math.round(m.score)}
                  <span style={{ fontSize: 12, color: "var(--muted)" }}> match</span>
                </div>
                <div className="match-bar">
                  <span style={{ width: `${Math.min(100, m.score)}%` }} />
                </div>
                {m.topic_status && (
                  <span className={`pill ${statusClass(m.topic_status)}`} style={{ marginTop: 6 }}>
                    {m.topic_status}
                  </span>
                )}
                {prior?.recommendation && (
                  <div style={{ marginTop: 6 }}>
                    <span className={`pill ${recClass(prior.recommendation)}`}>
                      {prior.recommendation}
                    </span>
                    {prior.fit_score != null && (
                      <div className="meta">fit {Math.round(prior.fit_score)}</div>
                    )}
                  </div>
                )}
                {vaultIndex[m.topic_id]?.cached_council && (
                  <div style={{ marginTop: 6 }}>
                    <span className="pill green">cached</span>
                  </div>
                )}
                {vaultIndex[m.topic_id]?.cached_flint && !vaultIndex[m.topic_id]?.cached_council && (
                  <div style={{ marginTop: 6 }}>
                    <span className="pill yellow">flint cached</span>
                  </div>
                )}
              </div>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="ghost small" onClick={() => track(m)}>
                Track
              </button>
              <button
                className="ghost small"
                onClick={() => flintOne(m)}
                disabled={flintBusy != null || deepRunning}
                title="Creative sparks from tools on the ME resume only. Does not run the full council."
              >
                {flintBusy === m.topic_id ? "Flint thinking…" : "Flint this topic"}
              </button>
              <button
                className="ghost small"
                onClick={() => councilOne(m)}
                disabled={deepRunning}
              >
                Council this topic
              </button>
              <Link
                to={`/work/${m.topic_id}`}
                state={{ topic: t }}
                className="ghost small"
                style={{ textDecoration: "none" }}
              >
                Open workspace →
              </Link>
              <Link to={`/topic/${m.topic_id}`} state={{ topic: t }} className="meta">
                Classic view
              </Link>
            </div>
            <WhyMatched topicId={m.topic_id} topicCode={m.topic_code} />
            {flintByTopic[m.topic_id] && (
              <div
                className="card"
                style={{ marginTop: 10, background: "var(--panel-2)", borderColor: "#e6c07b" }}
              >
                <FlintCard rec={flintByTopic[m.topic_id]} />
                <div style={{ marginTop: 10 }}>
                  <AgentChat
                    topicId={m.topic_id}
                    agent="Flint"
                    topicsMeta={m.topic ? { [m.topic_id]: topicMeta(m.topic) } : undefined}
                    compact
                  />
                </div>
              </div>
            )}
          </div>
        );
      })}

      {!scanning && matches.length === 0 && inbox?.scanned_at && (
        <div className="empty">
          No overlapping open topics in the cache. Try{" "}
          <button className="ghost small" onClick={() => scan(true)}>
            Re-rank from resume
          </button>{" "}
          or add more capability detail on <Link to="/profile">Profile</Link>.
        </div>
      )}

      {deepRuns.map((r) => (
        <CouncilCard key={r.id} run={r} />
      ))}
    </div>
  );
}
