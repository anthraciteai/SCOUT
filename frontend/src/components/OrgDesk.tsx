import { useEffect, useState } from "react";
import { OrgApi } from "../api";
import type { CollabOverlap, CollabReport, SbirWorkspace } from "../types";
import { useToast } from "../toast";
import FlintCard, { type FlintResult } from "./FlintCard";
import AgentChat from "./AgentChat";

function nameOf(collab: CollabReport | undefined, uid: string) {
  const card = collab?.cards?.find((c) => c.user_id === uid);
  return card?.display_name || uid;
}

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
  const [busy, setBusy] = useState<"shared" | "draft" | "collab" | "promote" | null>(null);
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
    return data;
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await load();
        if (cancelled) return;
        if (data.collab?.stale && (data.collab.cards?.length || 0) >= 2) {
          setBusy("collab");
          const next = await OrgApi.refreshCollab(topicId);
          if (cancelled) return;
          setWs((prev) => (prev ? { ...prev, collab: next } : prev));
        }
      } catch {
        /* desk still usable without collab note */
      } finally {
        if (!cancelled) setBusy(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId]);

  async function promote(overlap?: CollabOverlap) {
    if (!ws?.collab) return;
    const bullets = overlap
      ? [overlap.split, ...(ws.collab.promote || [])].filter((x): x is string => Boolean(x))
      : ws.collab.promote || [];
    if (!bullets.length) {
      toast("Nothing to insert yet — wait for Collier or save another draft.", "info");
      return;
    }
    setBusy("promote");
    try {
      const result = await OrgApi.promoteCollab(topicId, {
        theme: overlap?.theme || "Desk overlap",
        bullets,
        expected_sha: ws.collab.proposal_sha,
      });
      if (result.skipped) {
        toast("Already in the shared proposal");
      } else {
        toast("Inserted into shared proposal");
      }
      setShared(result.shared_proposal || "");
      setWs((prev) =>
        prev?.collab
          ? { ...prev, collab: { ...prev.collab, proposal_sha: result.proposal_sha }, shared_proposal: result.shared_proposal }
          : prev
      );
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        toast("Shared proposal changed — reloaded", "info");
        await load();
      } else {
        toast("Could not insert into shared proposal", "error");
      }
    } finally {
      setBusy(null);
    }
  }

  if (!ws) return null;
  const flint = ws.my_flint?.result as FlintResult | undefined;
  const collab = ws.collab;
  const overlaps = collab?.overlaps || [];
  const involved = new Set(overlaps.flatMap((o) => o.who));

  return (
    <div className="card" style={{ borderColor: "#e6c07b" }}>
      <div className="row spread">
        <div>
          <h3 style={{ margin: 0 }}>{topicCode || title || topicId}</h3>
          <div className="meta">
            {ws.paths?.shared} (federated) · {ws.paths?.mine} (yours)
          </div>
        </div>
        <div className="row">
          {ws.cached_council && <span className="pill green">council cached</span>}
          {ws.cached_flint && <span className="pill yellow">flint cached</span>}
          {(ws.chat_turns || 0) > 0 && (
            <span className="pill">{ws.chat_turns} chat turns</span>
          )}
          {overlaps.length > 0 && (
            <span className="pill yellow">{overlaps.length} overlap{overlaps.length === 1 ? "" : "s"}</span>
          )}
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
                {involved.has(t.user_id) ? " · overlap" : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="collab-panel">
        <div className="row spread" style={{ marginBottom: 6 }}>
          <div>
            <h3 style={{ margin: 0 }}>Approach overlap</h3>
            <p className="meta" style={{ margin: "4px 0 0" }}>
              Private drafts stay private. The desk only sees approach cards (Flint sparks + section names).
            </p>
          </div>
          <button
            className="ghost small"
            disabled={busy !== null || (collab?.cards?.length || 0) < 2}
            onClick={async () => {
              setBusy("collab");
              try {
                const next = await OrgApi.refreshCollab(topicId, true);
                setWs((prev) => (prev ? { ...prev, collab: next } : prev));
                toast(next.llm ? "Collier matched approaches" : "Overlap flags refreshed");
              } catch {
                toast("Could not refresh overlap", "error");
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === "collab" ? "Matching…" : "Match approaches"}
          </button>
        </div>

        {(collab?.cards?.length || 0) < 2 && (
          <div className="meta">
            Flags appear once two people run Flint or save a headed draft. Ken / Jake / Matt each keep their own
            prose.
          </div>
        )}

        {overlaps.map((o, i) => (
          <div className="collab-overlap" key={`${o.theme}-${i}`}>
            <div className="row spread">
              <strong>{o.theme}</strong>
              <span className="meta">{o.who.map((uid) => nameOf(collab, uid)).join(" · ")}</span>
            </div>
            {o.split && <p style={{ fontSize: 13, margin: "6px 0 0" }}>{o.split}</p>}
            {!!o.tools?.length && (
              <div className="row" style={{ gap: 6, marginTop: 8 }}>
                {o.tools.map((t) => (
                  <span className="tag" key={t}>
                    {t}
                  </span>
                ))}
              </div>
            )}
            <div style={{ marginTop: 8 }}>
              <button
                className="small"
                disabled={busy !== null}
                onClick={() => promote(o)}
              >
                Insert into shared
              </button>
            </div>
          </div>
        ))}

        {(collab?.gaps || []).map((g) => (
          <div className="meta" key={g} style={{ marginTop: 6 }}>
            {g}
          </div>
        ))}

        {!!collab?.promote?.length && (
          <div style={{ marginTop: 10 }}>
            <div className="kv">Collier — promote to shared/proposal.md</div>
            <ul className="tight">
              {collab.promote.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <button className="ghost small" disabled={busy !== null} onClick={() => promote()}>
              Insert all suggestions
            </button>
          </div>
        )}
      </div>

      <h3>Shared proposal</h3>
      <p className="meta">Everyone with an employees/&lt;you&gt; file can edit this. Helps Ken / Jake / Matt write together.</p>
      <textarea rows={8} value={shared} onChange={(e) => setShared(e.target.value)} />
      <div style={{ marginTop: 8 }}>
        <button
          className="ghost small"
          disabled={busy !== null}
          onClick={async () => {
            setBusy("shared");
            try {
              await OrgApi.saveShared(topicId, "proposal.md", shared, collab?.proposal_sha);
              toast("Shared proposal saved");
              const next = await load();
              setWs(next);
            } catch (err: unknown) {
              const status = (err as { response?: { status?: number } })?.response?.status;
              if (status === 409) {
                toast("Someone else saved first — reloaded their copy", "info");
                await load();
              } else {
                toast("Could not save shared proposal", "error");
              }
            } finally {
              setBusy(null);
            }
          }}
        >
          Save shared
        </button>
      </div>

      <h3>My private draft</h3>
      <p className="meta">Only you. Teammates see that you have a draft, not the text. Saving refreshes your approach card.</p>
      <textarea rows={6} value={draft} onChange={(e) => setDraft(e.target.value)} />
      <div style={{ marginTop: 8 }}>
        <button
          className="ghost small"
          disabled={busy !== null}
          onClick={async () => {
            setBusy("draft");
            try {
              await OrgApi.saveMine(topicId, "draft.md", draft);
              toast("Private draft saved");
              const next = await load();
              if (next.collab?.stale && (next.collab.cards?.length || 0) >= 2) {
                setBusy("collab");
                const note = await OrgApi.refreshCollab(topicId);
                setWs({ ...next, collab: note });
              }
            } catch {
              toast("Could not save draft", "error");
            } finally {
              setBusy(null);
            }
          }}
        >
          Save my draft
        </button>
      </div>

      {flint && (
        <div style={{ marginTop: 12 }}>
          <FlintCard rec={flint} />
          <div style={{ marginTop: 10 }}>
            <AgentChat topicId={topicId} agent="Flint" compact />
          </div>
        </div>
      )}
    </div>
  );
}
