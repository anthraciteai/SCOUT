import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { TrackerApi } from "../api";
import type { TrackedTopic } from "../types";

const OUTCOMES = ["", "pending", "awarded", "not_selected", "withdrawn"];

export default function Tracker() {
  const [rows, setRows] = useState<TrackedTopic[]>([]);
  const [stages, setStages] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const [r, s] = await Promise.all([TrackerApi.list(), TrackerApi.stages()]);
    setRows(r);
    setStages(s);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function update(id: number, body: { status?: string; notes?: string; outcome?: string }) {
    const updated = await TrackerApi.update(id, body);
    setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
  }

  async function remove(id: number) {
    if (!confirm("Remove from tracker?")) return;
    await TrackerApi.remove(id);
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  if (loading) return <div className="spinner">Loading tracker…</div>;

  return (
    <div>
      <h1>Tracker</h1>
      <p className="subtitle">
        Your bid pipeline. Move topics through stages and record outcomes. Lost bids can be improved
        by uploading the debrief in the <Link to="/debriefs">Debriefs</Link> tab.
      </p>

      {rows.length === 0 && (
        <div className="empty">
          Nothing tracked yet. Add topics from <Link to="/">Browse</Link>.
        </div>
      )}

      {rows.map((r) => (
        <div className="card" key={r.id}>
          <div className="row spread">
            <Link to={`/topic/${r.topic_id}`} className="topic-title">
              {r.topic_code} — {r.title}
            </Link>
            <button className="ghost small danger" onClick={() => remove(r.id)}>
              remove
            </button>
          </div>
          <div className="meta" style={{ margin: "4px 0 10px" }}>
            {r.component} · {r.program} · {r.topic_status}
          </div>
          <div className="row">
            <label className="kv">
              Stage&nbsp;
              <select value={r.status} onChange={(e) => update(r.id, { status: e.target.value })}>
                {stages.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label className="kv">
              Outcome&nbsp;
              <select
                value={r.outcome || ""}
                onChange={(e) => update(r.id, { outcome: e.target.value })}
              >
                {OUTCOMES.map((o) => (
                  <option key={o} value={o}>
                    {o ? o.replace(/_/g, " ") : "—"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <textarea
            style={{ marginTop: 10 }}
            rows={2}
            defaultValue={r.notes}
            placeholder="Notes…"
            onBlur={(e) => {
              if (e.target.value !== r.notes) update(r.id, { notes: e.target.value });
            }}
          />
        </div>
      ))}
    </div>
  );
}
