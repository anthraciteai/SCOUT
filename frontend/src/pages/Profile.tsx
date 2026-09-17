import { useEffect, useRef, useState } from "react";
import { ResumeApi } from "../api";
import type { ResumeInfo } from "../types";
import { useToast } from "../toast";

export default function Profile() {
  const [resumes, setResumes] = useState<ResumeInfo[]>([]);
  const [me, setMe] = useState<ResumeInfo | null>(null);
  const [active, setActive] = useState<ResumeInfo | null>(null);
  const [text, setText] = useState("");
  const [name, setName] = useState("ME");
  const [busy, setBusy] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const meFile = useRef<HTMLInputElement>(null);
  const companyFile = useRef<HTMLInputElement>(null);
  const toast = useToast();

  async function loadAll() {
    const [rs, act, mine] = await Promise.all([
      ResumeApi.list(),
      ResumeApi.active(),
      ResumeApi.me(),
    ]);
    setResumes(rs);
    setActive(act);
    setMe(mine);
    if (mine?.text) {
      setText(mine.text);
      setName(mine.name || "ME");
    } else if (act?.text && act.kind !== "company") {
      setText(act.text);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function saveMe() {
    setBusy(true);
    try {
      await ResumeApi.fromText(name || "ME", text, "me");
      await loadAll();
      toast("Saved as ME — Flint will use this toolbox");
    } finally {
      setBusy(false);
    }
  }

  async function uploadMe() {
    const file = meFile.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const r = await ResumeApi.upload(file, "ME", "me");
      setText(r.text || "");
      if (meFile.current) meFile.current.value = "";
      await loadAll();
      toast("This is you. Flint will only spark from tools on that resume.");
    } finally {
      setBusy(false);
    }
  }

  async function uploadCompany() {
    const file = companyFile.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      await ResumeApi.upload(file, file.name, "company");
      if (companyFile.current) companyFile.current.value = "";
      await loadAll();
      toast("Company pack updated");
    } finally {
      setBusy(false);
    }
  }

  async function activate(id: number) {
    await ResumeApi.update(id, { is_active: true });
    await loadAll();
  }
  async function markMe(id: number) {
    await ResumeApi.update(id, { kind: "me", is_active: true });
    await loadAll();
    toast("Marked as ME");
  }
  async function remove(id: number) {
    if (!confirm("Delete this profile?")) return;
    await ResumeApi.remove(id);
    await loadAll();
  }

  async function extract() {
    setExtracting(true);
    try {
      const r = await ResumeApi.extract(undefined, true);
      setActive(r);
      toast("Matcher keywords refreshed");
      await loadAll();
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Extract failed", "error");
    } finally {
      setExtracting(false);
    }
  }

  const extractData = (me || active)?.extract;
  const company = resumes.find((r) => r.kind !== "me");

  return (
    <div>
      <h1>Profile</h1>
      <p className="subtitle">
        Upload a resume and mark it <strong>ME</strong>. Flint — the creative agent — will only
        invent approaches from tools you actually have.
      </p>

      <div className="card" style={{ borderColor: "var(--accent)" }}>
        <h2 style={{ marginTop: 0 }}>This is ME</h2>
        <p className="meta" style={{ marginTop: 0 }}>
          Your person: jobs, languages, platforms, hardware. Not the company one-pager.
          {me ? ` Loaded: ${me.name} (${me.chars} chars).` : " Nothing marked ME yet."}
        </p>
        <div className="row" style={{ marginBottom: 10 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="ME" />
          <input type="file" ref={meFile} accept=".pdf,.docx,.txt" />
          <button onClick={uploadMe} disabled={busy}>
            Upload as ME
          </button>
        </div>
        <textarea
          rows={14}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste your resume. Flint reads this as you — Docker, PX4, TAK, Python, Jetson, whatever is actually on the page."
        />
        <div style={{ marginTop: 10 }}>
          <button onClick={saveMe} disabled={busy || !text.trim()}>
            Save as ME
          </button>
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Company / products</h2>
        <p className="meta" style={{ marginTop: 0 }}>
          VEIN / CANARI / DAVY pack used for inbox ranking. Stays separate from ME so Flint
          does not confuse a product brochure with your hands-on tools.
          {company ? ` Active: ${company.name}.` : ""}
        </p>
        <div className="row">
          <input type="file" ref={companyFile} accept=".pdf,.docx,.txt" />
          <button className="ghost" onClick={uploadCompany} disabled={busy}>
            Upload company pack
          </button>
        </div>
      </div>

      {resumes.length > 0 && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>All profiles</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Kind</th>
                <th>Chars</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {resumes.map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td>
                    {r.kind === "me" ? (
                      <span className="pill green">ME</span>
                    ) : (
                      <span className="pill muted">company</span>
                    )}
                  </td>
                  <td>{r.chars}</td>
                  <td>
                    {r.kind !== "me" && (
                      <button className="ghost small" onClick={() => markMe(r.id)}>
                        this is ME
                      </button>
                    )}{" "}
                    {!r.is_active && (
                      <button className="ghost small" onClick={() => activate(r.id)}>
                        activate
                      </button>
                    )}{" "}
                    <button className="ghost small danger" onClick={() => remove(r.id)}>
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <div className="row spread">
          <h2 style={{ marginTop: 0 }}>Matcher keywords</h2>
          <button className="ghost small" onClick={extract} disabled={extracting}>
            {extracting ? "Extracting…" : "Refresh extract"}
          </button>
        </div>
        {extractData?.summary && <p style={{ fontSize: 14 }}>{extractData.summary}</p>}
        {(extractData?.search_queries || []).length > 0 && (
          <div className="row" style={{ gap: 6 }}>
            {extractData!.search_queries!.map((q) => (
              <span className="tag" key={q}>
                {q}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
