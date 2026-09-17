import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { TopicsApi, TrackerApi } from "../api";
import type { TopicScope } from "../api";
import type { Topic } from "../types";
import { useSelection } from "../selection";
import { useToast } from "../toast";

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
    toast(`Added ${topicCode(t)} to tracker`);
  }

  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      <h1>Browse</h1>
      <p className="subtitle">
        Catalog search if you already know what to look for. The Inbox ranks open topics against
        your profile without this step.
      </p>

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
