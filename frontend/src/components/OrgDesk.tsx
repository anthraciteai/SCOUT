import { useEffect, useState } from "react";
import { OrgApi } from "../api";
import type { SbirWorkspace } from "../types";
import { useToast } from "../toast";
import FlintCard, { type FlintResult } from "./FlintCard";

export default function OrgDesk({
  topicId,
  title,
  topicCode,
}: {
  topicId: string;
  title?: string;
  topicCode?: string;
}) {
  const [ws, setWs] = useState<SbirWorkspace | null>(null);
  const [shared, setShared] = useState("");
  const [draft, setDraft] = useState("");
  const toast = useToast();

  async function load() {
    const data = await OrgApi.grant(topicId, {
      topic_id: topicId,
      title: title || "",
      topic_code: topicCode || "",
    });
    setWs(data);
    setShared(data.shared_proposal || "");
    setDraft(data.my_draft || "");
  }

  useEffect(() => {
    load().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId]);

  if (!ws) return null;
  const flint = ws.my_flint?.result as FlintResult | undefined;

  return (
    <div className="card" style={{ borderColor: "#e6c07b" }}>
      <div className="row spread">
        <div>
          <h3 style={{ margin: 0 }}>Group desk</h3>
          <div className="meta">
            {ws.paths?.shared} (federated) · {ws.paths?.mine} (yours)
          </div>
        </div>
        <div className="row">
          {ws.cached_council && <span className="pill green">council cached</span>}
          {ws.cached_flint && <span className="pill yellow">flint cached</span>}
        </div>
      </div>

      {ws.teammates && ws.teammates.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="kv">Teammates on this org</div>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            {ws.teammates.map((t) => (
              <span className="tag" key={t.user_id} title={t.skills.join(", ")}>
                {t.display_name}
                {t.has_draft ? " · writing" : ""}
                {t.has_flint ? " · flint" : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      <h3>Shared proposal</h3>
      <p className="meta">Everyone in employees.txt can edit this. Helps Ken / Jake / Matt write together.</p>
      <textarea rows={8} value={shared} onChange={(e) => setShared(e.target.value)} />
      <div style={{ marginTop: 8 }}>
        <button
          className="ghost small"
          onClick={async () => {
            await OrgApi.saveShared(topicId, "proposal.md", shared);
            toast("Shared proposal saved");
          }}
        >
          Save shared
        </button>
      </div>

      <h3>My private draft</h3>
      <p className="meta">Only you. Teammates see that you have a draft, not the text.</p>
      <textarea rows={6} value={draft} onChange={(e) => setDraft(e.target.value)} />
      <div style={{ marginTop: 8 }}>
        <button
          className="ghost small"
          onClick={async () => {
            await OrgApi.saveMine(topicId, "draft.md", draft);
            toast("Private draft saved");
          }}
        >
          Save my draft
        </button>
      </div>

      {flint && (
        <div style={{ marginTop: 12 }}>
          <FlintCard rec={flint} />
        </div>
      )}
    </div>
  );
}
