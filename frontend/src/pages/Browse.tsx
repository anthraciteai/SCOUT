import { useEffect, useState } from "react";
import ComponentBreakdown from "../components/ComponentBreakdown";
import RerankDialog from "../components/RerankDialog";
import type { ScanBody } from "../api";
import { Link, useNavigate } from "react-router-dom";
import { MatchesApi, TopicsApi, TrackerApi } from "../api";
import type { TopicScope } from "../api";
import type { MatchInbox, MatchItem, Topic } from "../types";
import { useSelection } from "../selection";
import { useToast } from "../toast";
import { matchBadge, scoreClass } from "../matchRank";

const PAGE_SIZE = 10;

export function topicCode(t: Topic) {
  return t.topicCode || t.finalTopicCode || "";
}
export function topicTitle(t: Topic) {
  return t.topicTitle || t.title || "(untitled)";
}
export function statusClass(s?: string) {
  const v = (s || "").toLowerCase();
  if (v.includes("open")) return "green";
  if (v.includes("pre")) return "yellow";
  return "muted";
}

export function fmtDate(ms?: number): string {
  if (!ms || typeof ms !== "number") return "—";
  try {
    return new Date(ms).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "—";
  }
}

/** Render the key release + due/close dates for a topic. */
export function TopicDates({ t }: { t: Topic }) {
  const preStart = t.topicPreReleaseStartDate;
  const openStart = t.topicStartDate;
  const close = t.topicEndDate; // proposals due / topic close
  return (
    <div className="row" style={{ gap: 14, flexWrap: "wrap" }}>
      {preStart && (
        <span className="meta">
          <strong>Pre-release:</strong> {fmtDate(preStart)}
        </span>
      )}
      {openStart && (
        <span className="meta">
          <strong>Opens:</strong> {fmtDate(openStart)}
        </span>
      )}
      <span className="meta" style={{ color: close ? "var(--text)" : "var(--muted)" }}>
        <strong>Due/Close:</strong> {fmtDate(close)}
      </span>
    </div>
  );
}

export function topicMeta(t: Topic) {
  return {
    topic_code: topicCode(t) || undefined,
    title: t.topicTitle || t.title || undefined,
    component: t.component,
    program: t.program,
    topic_status: t.topicStatus,
    solicitation_title: t.solicitationTitle,
  };
}

export default function Browse() {
  const [searchText, setSearchText] = useState("");
  const [scope, setScope] = useState<TopicScope>("open");
  const [program, setProgram] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<Topic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [inbox, setInbox] = useState<MatchInbox | null>(null);
  const [ranking, setRanking] = useState(false);
  const [rerankOpen, setRerankOpen] = useState(false);

  const { toggle, isSelected, ids } = useSelection();
  const navigate = useNavigate();
  const toast = useToast();

  async function load(p = page) {
    setLoading(true);
    setError("");
    try {
      const res = await TopicsApi.search({
        searchText: searchText || undefined,
        scope,
        program: program || undefined,
        size: PAGE_SIZE,
        page: p,
      });
      setData(res.data || []);
      setTotal(res.total || 0);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Search failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    MatchesApi.list().then(setInbox).catch(() => {});
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setPage(0);
    load(0);
  }

  function go(p: number) {
    setPage(p);
    load(p);
  }

  async function rerank() {
    setRerankOpen(true);
  }

  async function runScan(body: ScanBody) {
    setRanking(true);
    try {
      const data = await MatchesApi.scan(body);
      setInbox(data);
      toast(`Cached ${data.matches.length} ranked topic${data.matches.length === 1 ? "" : "s"}`);
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Re-rank failed", "error");
    } finally {
      setRanking(false);
      setRerankOpen(false);
    }
  }

  async function track(t: Topic) {
    await TrackerApi.track({
      topic_id: t.topicId,
      topic_code: topicCode(t),
      title: topicTitle(t),
      component: t.component,
      program: t.program,
      topic_status: t.topicStatus,
      raw: t,
    });
    toast(`Added ${topicCode(t)} to pipeline — Group desk is for that bid`);
  }

  const pages = Math.ceil(total / PAGE_SIZE);
  const byId = new Map((inbox?.matches || []).map((m) => [m.topic_id, m]));
  const best = (inbox?.matches || []).filter((m) => m.score > 0).slice(0, 12);
  const stale =
    Boolean(inbox?.resume?.updated_at && inbox?.scanned_at) &&
    new Date(inbox!.resume!.updated_at as string).getTime() >
      new Date(inbox!.scanned_at as string).getTime();

  function MatchSide({ m }: { m?: MatchItem }) {
    if (!m) return null;
    const badge = matchBadge(m.score);
    return (
      <div style={{ textAlign: "right", minWidth: 96 }}>
        {badge && (
          <span className={`pill ${badge.cls}`} style={{ marginBottom: 6 }}>
            {badge.text}
          </span>
        )}
        <div className={`score ${scoreClass(m.score)}`} style={{ fontSize: 20 }}>
          {Math.round(m.score)}
          <span style={{ fontSize: 12, color: "var(--muted)" }}> match</span>
        </div>
        <div className="match-bar">
          <span style={{ width: `${Math.min(100, m.score)}%` }} />
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
        running={ranking}
      />
      <h1>Browse</h1>
      <p className="subtitle">
        Strong matches come from the last ranking of your resume — they stay cached until you
        re-rank. Catalog search is still here if you already know a keyword.
      </p>

      <ComponentBreakdown topics={data.length ? data : (inbox?.matches || []).map((m) => m.topic).filter(Boolean) as Topic[]} />

      <div className="card">
        <div className="row spread">
          <div>
            <div className="meta">
              {inbox?.scanned_at
                ? `Cached ${inbox.match_count} topics · ranked ${new Date(inbox.scanned_at).toLocaleString()}`
                : "No cached ranking yet."}
              {stale && (
                <span style={{ color: "var(--yellow)", marginLeft: 8 }}>
                  Resume changed since this cache.
                </span>
              )}
            </div>
          </div>
          <button onClick={rerank} disabled={ranking}>
            {ranking ? "Re-ranking…" : "Re-rank from resume"}
          </button>
        </div>
        <p className="meta" style={{ margin: "8px 0 0" }}>
          Re-rank walks every open SBIR against ME / the company pack. It can take several
          minutes. Browse itself only reads the cache.
        </p>
      </div>

      {best.length > 0 && (
        <>
          <h2>Strong matches</h2>
          <p className="meta" style={{ marginTop: 0 }}>
            Highest overlap from the cached scan. Not a new LLM run.
          </p>
          {best.map((m) => {
            const t = m.topic;
            return (
              <div className="card" key={`best-${m.topic_id}`}>
                <div className="row spread">
                  <div className="grow">
                    <div className="row">
                      {t && (
                        <input
                          type="checkbox"
                          checked={isSelected(m.topic_id)}
                          onChange={() => toggle(t)}
                          style={{ width: 16, height: 16 }}
                        />
                      )}
                      <Link to={`/topic/${m.topic_id}`} state={{ topic: t }} className="topic-title">
                        {m.topic_code} — {m.title}
                      </Link>
                    </div>
                    <div className="meta" style={{ marginTop: 4 }}>
                      {m.component} · {m.program}
                    </div>
                    {t && (
                      <div style={{ marginTop: 6 }}>
                        <TopicDates t={t} />
                      </div>
                    )}
                  </div>
                  <div className="row">
                    <MatchSide m={m} />
                    {t && (
                      <button className="ghost small" onClick={() => track(t)}>
                        Track
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </>
      )}

      <h2>Catalog</h2>
      <form className="card" onSubmit={submit}>
        <div className="row">
          <input
            className="grow"
            placeholder="Search topic text, keywords…"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <select value={scope} onChange={(e) => setScope(e.target.value as TopicScope)}>
            <option value="open">Open + Pre-Release</option>
            <option value="openonly">Open only</option>
            <option value="prerelease">Pre-Release only</option>
            <option value="all">All (incl. closed)</option>
          </select>
          <select value={program} onChange={(e) => setProgram(e.target.value)}>
            <option value="">SBIR + STTR</option>
            <option value="SBIR">SBIR</option>
            <option value="STTR">STTR</option>
          </select>
          <button type="submit" disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
      </form>

      {error && <div className="card" style={{ color: "var(--red)" }}>{error}</div>}

      <div className="row spread" style={{ marginBottom: 10 }}>
        <span className="meta">{total} topics found</span>
        {pages > 1 && (
          <div className="row">
            <button className="ghost small" disabled={page <= 0} onClick={() => go(page - 1)}>
              ← Prev
            </button>
            <span className="meta">
              Page {page + 1} / {pages}
            </span>
            <button
              className="ghost small"
              disabled={page + 1 >= pages}
              onClick={() => go(page + 1)}
            >
              Next →
            </button>
          </div>
        )}
      </div>

      {data.map((t) => (
        <div className="card" key={t.topicId}>
          <div className="row spread">
            <div className="grow">
              <div className="row">
                <input
                  type="checkbox"
                  checked={isSelected(t.topicId)}
                  onChange={() => toggle(t)}
                  style={{ width: 16, height: 16 }}
                />
                <Link to={`/topic/${t.topicId}`} state={{ topic: t }} className="topic-title">
                  {topicCode(t)} — {topicTitle(t)}
                </Link>
              </div>
              <div className="meta" style={{ marginTop: 4 }}>
                {t.component} · {t.program} · {t.solicitationTitle}
                {typeof t.noOfPublishedQuestions === "number" && (
                  <> · {t.noOfPublishedQuestions} Q&amp;A</>
                )}
              </div>
              <div style={{ marginTop: 6 }}>
                <TopicDates t={t} />
              </div>
            </div>
            <div className="row">
              <MatchSide m={byId.get(t.topicId)} />
              <span className={`pill ${statusClass(t.topicStatus)}`}>{t.topicStatus}</span>
              <button className="ghost small" onClick={() => track(t)}>
                Track
              </button>
            </div>
          </div>
        </div>
      ))}

      {!loading && data.length === 0 && <div className="empty">No topics match your filters.</div>}

      {ids.length > 0 && (
        <div className="selbar">
          <span>
            <strong>{ids.length}</strong> topic{ids.length > 1 ? "s" : ""} selected
          </span>
          <button onClick={() => navigate("/analysis")}>Run council →</button>
        </div>
      )}
    </div>
  );
}
