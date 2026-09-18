import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { OrgApi, TrackerApi } from "../api";
import type { SbirWorkspace, TrackedTopic } from "../types";
import OrgDesk from "../components/OrgDesk";

export default function GroupDesk() {
  const { topicId } = useParams();
  const navigate = useNavigate();
  const [tracked, setTracked] = useState<TrackedTopic[]>([]);
  const [workspaces, setWorkspaces] = useState<Record<string, SbirWorkspace>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [rows, sbirs] = await Promise.all([TrackerApi.list(), OrgApi.sbirs().catch(() => [])]);
        setTracked(rows);
        setWorkspaces(Object.fromEntries((sbirs || []).map((s) => [s.topic_id, s])));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!loading && !topicId && tracked.length === 1) {
      navigate(`/desk/${tracked[0].topic_id}`, { replace: true });
    }
  }, [loading, topicId, tracked, navigate]);

  const selected = tracked.find((r) => r.topic_id === topicId) || null;
  const ws = selected ? workspaces[selected.topic_id] : undefined;
  const writers = ws?.writers || [];

  if (loading) return <div className="spinner">Loading group desk…</div>;

  if (tracked.length === 0) {
    return (
      <div>
        <h1>Group desk</h1>
        <p className="subtitle">
          Shared writing for SBIRs the company is actually bidding. Track a topic from Inbox or
          Browse first — browsing the catalog does not open a desk.
        </p>
        <div className="empty">
          Nothing tracked. Add a topic to <Link to="/tracker">Pipeline</Link>, then Ken / Jake /
          Matt can overlap approaches here without sharing private drafts.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1>Group desk</h1>
      <p className="subtitle">
        Only tracked SBIRs. Overlap matching is for when more than one person on the roster is
        writing. Teammates see that a draft exists, not the private text.
      </p>

      <div className="card">
        {tracked.map((r) => {
          const w = workspaces[r.topic_id];
          const n = w?.writers?.length || 0;
          const active = r.topic_id === topicId;
          return (
            <button
              key={r.id}
              className={active ? "small" : "ghost small"}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                marginBottom: 8,
                padding: "10px 12px",
              }}
              onClick={() => navigate(`/desk/${r.topic_id}`)}
            >
              <div className="row spread">
                <span>
                  <strong>
                    {r.topic_code || r.topic_id} — {r.title}
                  </strong>
                  <div className="meta">
                    {r.status.replace(/_/g, " ")}
                    {n > 0 ? ` · ${n} writer${n === 1 ? "" : "s"}` : ""}
                    {n < 2 ? " · waiting on a teammate" : ""}
                  </div>
                </span>
                <span className="row">
                  {n >= 2 && <span className="pill green">group</span>}
                  {(w?.overlap_count || 0) > 0 && (
                    <span className="pill yellow">{w?.overlap_count} overlap</span>
                  )}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {!selected && (
        <div className="empty">Pick a tracked SBIR above to open the shared desk.</div>
      )}

      {selected && (
        <OrgDesk
          topicId={selected.topic_id}
          title={selected.title}
          topicCode={selected.topic_code}
        />
      )}

      {selected && writers.length < 2 && (
        <p className="meta">
          {writers.length === 1
            ? `${writers[0]} is on this desk. Match approaches unlocks when a second teammate writes.`
            : "Open this desk (Flint or a private draft) so teammates can join."}{" "}
          <Link to={`/topic/${selected.topic_id}`}>Topic page →</Link>
        </p>
      )}
    </div>
  );
}
