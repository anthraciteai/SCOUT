import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { OrgApi } from "../api";
import type { OrgCompany, OrgEmployee, SbirWorkspace } from "../types";
import { useAuth } from "../auth";
import { useToast } from "../toast";

interface EmployeeDraft {
  display_name: string;
  skills: string; // comma-separated for the input
}

interface ResumeMeta {
  filename?: string | null;
  chars: number;
  resume_sha?: string;
  updated_at?: string;
}

export default function Org() {
  const { user } = useAuth();
  const [co, setCo] = useState<OrgCompany | null>(null);
  const [sbirs, setSbirs] = useState<SbirWorkspace[]>([]);
  const [mission, setMission] = useState("");
  const [products, setProducts] = useState("");
  const [editing, setEditing] = useState<string | null>(null); // user_id being edited
  const [draft, setDraft] = useState<EmployeeDraft>({ display_name: "", skills: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [hireOpen, setHireOpen] = useState(false);
  const [hireDraft, setHireDraft] = useState<{
    user_id: string;
    display_name: string;
    skills: string;
  }>({ user_id: "", display_name: "", skills: "" });
  const [resumes, setResumes] = useState<Record<string, ResumeMeta>>({});
  const [previewFor, setPreviewFor] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string>("");
  const toast = useToast();

  async function load() {
    const [c, s] = await Promise.all([OrgApi.company(), OrgApi.sbirs()]);
    setCo(c);
    setMission(c.mission);
    setProducts(c.products);
    setSbirs(s);
    loadResumes(c.employees.map((e) => e.user_id));
  }

  async function loadResumes(uids: string[]) {
    const entries = await Promise.all(
      uids.map(async (uid) => {
        try {
          const r = await OrgApi.employeeResume(uid);
          return [
            uid,
            {
              filename: r.filename,
              chars: r.chars,
              resume_sha: r.resume_sha,
              updated_at: r.updated_at,
            } as ResumeMeta,
          ] as const;
        } catch {
          return [uid, { chars: 0 } as ResumeMeta] as const;
        }
      })
    );
    setResumes(Object.fromEntries(entries));
  }

  async function attachResume(uid: string, file: File | null | undefined) {
    if (!file) return;
    setBusy(uid);
    try {
      const res = await OrgApi.uploadEmployeeResume(uid, file);
      toast(`Attached ${res.filename || file.name} (${res.chars} chars) to ${uid}. Re-tagging.`);
      await loadResumes([uid]);
    } catch (err: any) {
      toast(err?.response?.data?.detail || err.message || "Upload failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function detachResume(uid: string) {
    if (!confirm(`Remove ${uid}'s resume? Their tag pack will drop back to just company products.`)) {
      return;
    }
    setBusy(uid);
    try {
      await OrgApi.deleteEmployeeResume(uid);
      toast(`Cleared ${uid}'s resume`);
      await loadResumes([uid]);
      if (previewFor === uid) {
        setPreviewFor(null);
        setPreviewText("");
      }
    } catch (err: any) {
      toast(err?.response?.data?.detail || err.message || "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function togglePreview(uid: string) {
    if (previewFor === uid) {
      setPreviewFor(null);
      setPreviewText("");
      return;
    }
    setPreviewFor(uid);
    setPreviewText("Loading…");
    try {
      const r = await OrgApi.employeeResume(uid);
      setPreviewText(r.text || "(empty)");
    } catch (err: any) {
      setPreviewText(err?.response?.data?.detail || err.message || "Failed to load");
    }
  }

  function startEdit(e: OrgEmployee) {
    setEditing(e.user_id);
    setDraft({ display_name: e.display_name, skills: e.skills.join(", ") });
  }

  function cancelEdit() {
    setEditing(null);
    setDraft({ display_name: "", skills: "" });
  }

  async function saveEdit(uid: string) {
    setBusy(uid);
    try {
      await OrgApi.editEmployee(uid, {
        display_name: draft.display_name.trim() || uid,
        skills: draft.skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      toast(`Saved ${uid}. Re-tagging their pack in the background.`);
      cancelEdit();
      await load();
    } catch (err: any) {
      toast(err?.response?.data?.detail || err.message || "Save failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeEmployee(uid: string) {
    if (uid === user?.user_id) {
      toast("You can't remove yourself.", "error");
      return;
    }
    if (!confirm(`Remove ${uid} from ${co?.company_id}? Their user files stay; only the gate is removed.`)) {
      return;
    }
    setBusy(uid);
    try {
      await OrgApi.unhireEmployee(uid);
      toast(`${uid} removed`);
      await load();
    } catch (err: any) {
      toast(err?.response?.data?.detail || err.message || "Remove failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function hire() {
    const uid = hireDraft.user_id.trim().toLowerCase();
    if (!uid) {
      toast("user_id is required", "error");
      return;
    }
    setBusy(uid);
    try {
      await OrgApi.hireEmployee(uid, {
        display_name: hireDraft.display_name.trim() || uid,
        skills: hireDraft.skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      toast(`Hired ${uid}. They now inherit the company product terms.`);
      setHireDraft({ user_id: "", display_name: "", skills: "" });
      setHireOpen(false);
      await load();
    } catch (err: any) {
      toast(err?.response?.data?.detail || err.message || "Hire failed", "error");
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    load().catch(() => {});
  }, []);

  if (!co) return <div className="spinner">Loading org…</div>;

  return (
    <div>
      <h1>{co.company_id}</h1>
      <p className="subtitle">
        Signed in as <strong>{user?.display_name || user?.user_id}</strong>. Company mission and
        Personal drafts stay under your user folder. Approach overlap on a topic is
        flagged on the group desk without sharing private prose.
      </p>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Mission</h2>
        <textarea rows={5} value={mission} onChange={(e) => setMission(e.target.value)} />
        <div style={{ marginTop: 8 }}>
          <button
            className="ghost"
            onClick={async () => {
              await OrgApi.saveMission(mission);
              toast("Mission saved for the org");
            }}
          >
            Save mission
          </button>
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Products</h2>
        <textarea rows={10} value={products} onChange={(e) => setProducts(e.target.value)} />
        <div style={{ marginTop: 8 }}>
          <button
            className="ghost"
            onClick={async () => {
              await OrgApi.saveProducts(products);
              toast("Products saved for the org");
            }}
          >
            Save products
          </button>
        </div>
      </div>

      <div className="card">
        <div className="row spread" style={{ alignItems: "baseline" }}>
          <div>
            <h2 style={{ margin: 0 }}>People in {co.company_id}</h2>
            <p className="meta" style={{ marginTop: 4 }}>
              From companies/{co.company_id}/employees/&lt;you&gt; — complementary stacks for a bid.
              Editing anyone re-tags their matching pack against the company products.
            </p>
          </div>
          <button
            className="small"
            onClick={() => {
              setHireOpen((x) => !x);
              setHireDraft({ user_id: "", display_name: "", skills: "" });
            }}
          >
            {hireOpen ? "Cancel" : "+ Hire"}
          </button>
        </div>

        {hireOpen && (
          <div
            style={{
              marginTop: 10,
              padding: 10,
              border: "1px dashed var(--accent)",
              borderRadius: 6,
              display: "grid",
              gridTemplateColumns: "1fr 1fr 2fr auto",
              gap: 8,
              alignItems: "center",
            }}
          >
            <input
              value={hireDraft.user_id}
              onChange={(e) => setHireDraft({ ...hireDraft, user_id: e.target.value })}
              placeholder="user_id (e.g. tim)"
            />
            <input
              value={hireDraft.display_name}
              onChange={(e) => setHireDraft({ ...hireDraft, display_name: e.target.value })}
              placeholder="Display name"
            />
            <input
              value={hireDraft.skills}
              onChange={(e) => setHireDraft({ ...hireDraft, skills: e.target.value })}
              placeholder="Skills (comma separated): PX4, ULog, ATAK…"
            />
            <button onClick={hire} disabled={busy === hireDraft.user_id}>
              {busy === hireDraft.user_id ? "Hiring…" : "Hire"}
            </button>
          </div>
        )}

        <table style={{ marginTop: 10, width: "100%" }}>
          <thead>
            <tr>
              <th style={{ width: "20%" }}>Name</th>
              <th>Skills</th>
              <th style={{ width: 220 }}>Resume</th>
              <th style={{ width: 55, textAlign: "right" }}>SBIRs</th>
              <th style={{ width: 160, textAlign: "right" }}></th>
            </tr>
          </thead>
          <tbody>
            {co.employees.map((e) => {
              const isEditing = editing === e.user_id;
              const isSelf = e.user_id === user?.user_id;
              const resume = resumes[e.user_id];
              const hasResume = (resume?.chars || 0) > 0;
              const isPreviewing = previewFor === e.user_id;
              return (
                <Fragment key={e.user_id}>
                  <tr style={{ verticalAlign: "top" }}>
                    <td>
                      {isEditing ? (
                        <input
                          value={draft.display_name}
                          onChange={(ev) =>
                            setDraft({ ...draft, display_name: ev.target.value })
                          }
                          placeholder="Display name"
                          style={{ width: "100%" }}
                        />
                      ) : (
                        <strong>{e.display_name}</strong>
                      )}
                      <div className="meta">
                        {e.user_id}
                        {isSelf ? " · you" : ""}
                      </div>
                    </td>
                    <td>
                      {isEditing ? (
                        <input
                          value={draft.skills}
                          onChange={(ev) =>
                            setDraft({ ...draft, skills: ev.target.value })
                          }
                          placeholder="PX4, ULog, ATAK, mission planning…"
                          style={{ width: "100%" }}
                        />
                      ) : (
                        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                          {e.skills.length === 0 && (
                            <span className="meta">no skills yet — click Edit</span>
                          )}
                          {e.skills.map((s) => (
                            <span className="tag" key={s}>
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td>
                      {hasResume ? (
                        <div>
                          <div style={{ fontSize: 12 }}>
                            <strong style={{ wordBreak: "break-all" }}>
                              {resume?.filename || "resume"}
                            </strong>
                          </div>
                          <div className="meta" style={{ fontSize: 11 }}>
                            {resume?.chars.toLocaleString()} chars
                          </div>
                          <div
                            className="row"
                            style={{ gap: 4, marginTop: 4, flexWrap: "wrap" }}
                          >
                            <label
                              className="ghost small"
                              style={{
                                cursor: "pointer",
                                padding: "2px 8px",
                                fontSize: 11,
                              }}
                            >
                              Replace
                              <input
                                type="file"
                                accept=".pdf,.docx,.txt,.md"
                                style={{ display: "none" }}
                                onChange={(ev) =>
                                  attachResume(e.user_id, ev.target.files?.[0])
                                }
                                disabled={busy === e.user_id}
                              />
                            </label>
                            <button
                              className="ghost small"
                              style={{ fontSize: 11, padding: "2px 8px" }}
                              onClick={() => togglePreview(e.user_id)}
                            >
                              {isPreviewing ? "Hide" : "Preview"}
                            </button>
                            <button
                              className="ghost small danger"
                              style={{ fontSize: 11, padding: "2px 8px" }}
                              onClick={() => detachResume(e.user_id)}
                              disabled={busy === e.user_id}
                            >
                              clear
                            </button>
                          </div>
                        </div>
                      ) : (
                        <label
                          className="small"
                          style={{
                            cursor: "pointer",
                            padding: "4px 10px",
                            fontSize: 12,
                            display: "inline-block",
                          }}
                        >
                          {busy === e.user_id ? "Uploading…" : "+ Attach resume"}
                          <input
                            type="file"
                            accept=".pdf,.docx,.txt,.md"
                            style={{ display: "none" }}
                            onChange={(ev) =>
                              attachResume(e.user_id, ev.target.files?.[0])
                            }
                            disabled={busy === e.user_id}
                          />
                        </label>
                      )}
                    </td>
                    <td className="meta" style={{ textAlign: "right" }}>
                      {e.sbirs.length}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {isEditing ? (
                        <div
                          className="row"
                          style={{ gap: 6, justifyContent: "flex-end" }}
                        >
                          <button
                            className="small"
                            onClick={() => saveEdit(e.user_id)}
                            disabled={busy === e.user_id}
                          >
                            {busy === e.user_id ? "Saving…" : "Save"}
                          </button>
                          <button
                            className="ghost small"
                            onClick={cancelEdit}
                            disabled={busy === e.user_id}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div
                          className="row"
                          style={{ gap: 6, justifyContent: "flex-end" }}
                        >
                          <button
                            className="ghost small"
                            onClick={() => startEdit(e)}
                            disabled={busy === e.user_id}
                          >
                            Edit
                          </button>
                          {!isSelf && (
                            <button
                              className="ghost small danger"
                              onClick={() => removeEmployee(e.user_id)}
                              disabled={busy === e.user_id}
                            >
                              remove
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                  {isPreviewing && (
                    <tr>
                      <td colSpan={5} style={{ padding: 0 }}>
                        <div
                          style={{
                            margin: "6px 8px 12px",
                            padding: 10,
                            borderRadius: 6,
                            border: "1px solid var(--border)",
                            background: "rgba(255,255,255,0.02)",
                          }}
                        >
                          <div className="row spread" style={{ marginBottom: 4 }}>
                            <strong style={{ fontSize: 12 }}>
                              {e.display_name} · {resume?.filename || "resume"}
                            </strong>
                            <span className="meta" style={{ fontSize: 11 }}>
                              Extracted via Docling, stored as{" "}
                              <code>users/{e.user_id}/me.md</code>
                            </span>
                          </div>
                          <pre
                            className="stream"
                            style={{
                              whiteSpace: "pre-wrap",
                              fontSize: 12,
                              maxHeight: 240,
                              overflow: "auto",
                              margin: 0,
                            }}
                          >
                            {previewText}
                          </pre>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Federated SBIRs</h2>
        <p className="meta">
          Union of your sbir.txt and group capture/sbir.txt. Cached council/Flint skip the LLM.
          Shared writing is on Group desk, and only for SBIRs in the pipeline.
        </p>
        {sbirs.length === 0 && <div className="empty">None yet — Flint or Council a topic from Inbox.</div>}
        {sbirs.map((s) => (
          <div key={s.topic_id} className="row spread" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
            <div>
              <Link to={`/topic/${s.topic_id}`} className="topic-title">
                {s.topic_code || s.topic_id} — {s.title}
              </Link>
              <div className="meta">writers: {s.writers.join(", ") || "—"}</div>
            </div>
            <div className="row">
              {s.cached_council && <span className="pill green">council cached</span>}
              {s.cached_flint && <span className="pill yellow">flint cached</span>}
              {(s.chat_turns || 0) > 0 && <span className="pill">{s.chat_turns} chat turns</span>}
              {s.has_shared_proposal && <span className="pill">shared draft</span>}
              {(s.overlap_count || 0) > 0 && (
                <span className="pill yellow">
                  {s.overlap_count} overlap{s.overlap_count === 1 ? "" : "s"}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
