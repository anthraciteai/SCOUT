import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { TopicsApi } from "../api";
import type { Topic } from "../types";
import { topicCode, topicTitle, statusClass } from "../pages/Browse";

interface Props {
  value: string;
  onChange: (sel: { topic_id: string; topic_code?: string; title?: string }) => void;
}

// The /details endpoint often lacks title/code; build a best-effort label.
function label(t: Topic): string {
  const code = topicCode(t);
  const title = t.topicTitle || t.title;
  if (code && title) return `${code} — ${title}`;
  if (title) return title;
  const kw = (t as any).keywords as string | undefined;
  if (kw) return `Topic linked · ${kw.split(";")[0].trim()}`;
  return `Topic linked (${t.topicId})`;
}

function snippet(t: Topic): string {
  const obj = (t.objective || (t as any).topicObjective || "") as string;
  const text = obj.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return text ? text.slice(0, 140) + (text.length > 140 ? "…" : "") : "";
}

export default function TopicPicker({ value, onChange }: Props) {
  const [id, setId] = useState(value);
  const [resolved, setResolved] = useState<Topic | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error" | "ok">("idle");
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Topic[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const lastResolved = useRef<string>("");

  // When the parent value changes (e.g. switching proposals), resolve it once.
  useEffect(() => {
    setId(value);
    if (value && value !== lastResolved.current) {
      lookup(value, false);
    }
    if (!value) {
      setResolved(null);
      setState("idle");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  async function lookup(tid: string, emit = true) {
    const clean = tid.trim();
    if (!clean) return;
    setState("loading");
    try {
      const t = await TopicsApi.detail(clean);
      const merged = (t as any)?.topic ? { ...(t as any), ...(t as any).topic } : t;
      setResolved(merged);
      setState("ok");
      lastResolved.current = clean;
      if (emit)
        onChange({ topic_id: clean, topic_code: topicCode(merged), title: topicTitle(merged) });
    } catch {
      setResolved(null);
      setState("error");
    }
  }

  async function runSearch() {
    if (!search.trim()) return;
    setSearching(true);
    try {
      const res = await TopicsApi.search({ searchText: search, size: 8, scope: "all" });
      setResults(res.data || []);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  function pick(t: Topic) {
    setId(t.topicId);
    setResolved(t);
    setState("ok");
    lastResolved.current = t.topicId;
    setResults([]);
    setSearch("");
    setShowSearch(false);
    onChange({ topic_id: t.topicId, topic_code: topicCode(t), title: topicTitle(t) });
  }

  function clear() {
    setId("");
    setResolved(null);
    setState("idle");
    lastResolved.current = "";
    onChange({ topic_id: "", topic_code: undefined, title: undefined });
  }

  return (
    <div>
      <div className="row">
        <input
          className="grow"
          value={id}
          onChange={(e) => setId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              lookup(id);
            }
          }}
          placeholder="Link a topic: paste topic ID (e.g. 1d12a337…_86654)"
        />
        <button className="ghost" type="button" onClick={() => lookup(id)} disabled={state === "loading"}>
          {state === "loading" ? "Looking up…" : "Look up"}
        </button>
        <button className="ghost" type="button" onClick={() => setShowSearch((s) => !s)}>
          {showSearch ? "Hide search" : "Search by text"}
        </button>
        {(resolved || id) && (
          <button className="ghost small" type="button" onClick={clear}>
            clear
          </button>
        )}
      </div>

      {state === "error" && (
        <div className="meta" style={{ color: "var(--red)", marginTop: 6 }}>
          No topic found for that ID.
        </div>
      )}

      {resolved && state === "ok" && (
        <div
          className="card"
          style={{ marginTop: 8, padding: 10, background: "var(--panel-2)" }}
        >
          <div className="row spread">
            <Link
              to={`/topic/${resolved.topicId}`}
              state={{ topic: resolved }}
              className="topic-title"
            >
              ✓ {label(resolved)}
            </Link>
            {resolved.topicStatus && (
              <span className={`pill ${statusClass(resolved.topicStatus)}`}>
                {resolved.topicStatus}
              </span>
            )}
          </div>
          {(resolved.component || resolved.solicitationTitle) && (
            <div className="meta" style={{ marginTop: 4 }}>
              {[resolved.component, resolved.program, resolved.solicitationTitle]
                .filter(Boolean)
                .join(" · ")}
            </div>
          )}
          {snippet(resolved) && (
            <div className="meta" style={{ marginTop: 4 }}>
              {snippet(resolved)}
            </div>
          )}
        </div>
      )}

      {showSearch && (
        <div className="card" style={{ marginTop: 8, padding: 10 }}>
          <div className="row">
            <input
              className="grow"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  runSearch();
                }
              }}
              placeholder="Search open topics by keyword…"
            />
            <button type="button" onClick={runSearch} disabled={searching}>
              {searching ? "Searching…" : "Search"}
            </button>
          </div>
          <div className="meta" style={{ marginTop: 6 }}>
            Searches all topics (open and closed) so you can link older solicitations.
          </div>
          {results.map((t) => (
            <div key={t.topicId} className="row spread" style={{ padding: "6px 0" }}>
              <span style={{ fontSize: 13 }}>
                {topicCode(t)} — {topicTitle(t)}
              </span>
              <button className="ghost small" type="button" onClick={() => pick(t)}>
                use
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
