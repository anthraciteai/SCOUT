import { useEffect, useRef, useState } from "react";
import { DebriefsApi } from "../api";
import type { Debrief } from "../types";

export default function Debriefs() {
  const [rows, setRows] = useState<Debrief[]>([]);
  const [title, setTitle] = useState("Debrief");
  const [topicId, setTopicId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setRows(await DebriefsApi.list());
  }
  useEffect(() => {
    load();
  }, []);

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await DebriefsApi.upload(file, { title, topic_id: topicId || undefined });
      if (fileRef.current) fileRef.current.value = "";
      setTopicId("");
      await load();
    } finally {
      setUploading(false);
    }
  }

  async function analyze(id: number) {
    setAnalyzingId(id);
    try {
      const updated = await DebriefsApi.analyze(id);
      setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } finally {
      setAnalyzingId(null);
    }
  }

  async function remove(id: number) {
    if (!confirm("Delete this debrief?")) return;
    await DebriefsApi.remove(id);
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  return (
    <div>
      <h1>Debriefs</h1>
      <p className="subtitle">
        Upload government feedback / debriefs for proposals that weren't selected. Docling OCR
        extracts the text, then the LLM turns it into concrete lessons to strengthen future
        proposals (these feed the "Full review" in Proposals).
      </p>

      <div className="card">
        <div className="row">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
          />
          <input
            className="grow"
            value={topicId}
            onChange={(e) => setTopicId(e.target.value)}
            placeholder="Related topic ID (optional)"
          />
          <input type="file" ref={fileRef} accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff" />
          <button onClick={upload} disabled={uploading}>
            {uploading ? "Extracting…" : "Upload & extract"}
          </button>
        </div>
      </div>

      {rows.length === 0 && <div className="empty">No debriefs uploaded yet.</div>}

      {rows.map((d) => (
        <div className="card" key={d.id}>
          <div className="row spread">
            <div>
              <strong>{d.title}</strong>{" "}
              <span className="meta">
                {d.filename} · {new Date(d.created_at).toLocaleDateString()}
                {d.topic_id ? ` · topic ${d.topic_id}` : ""}
              </span>
            </div>
            <div className="row">
              <button
                className="ghost small"
                onClick={() => analyze(d.id)}
                disabled={analyzingId === d.id}
              >
                {analyzingId === d.id ? "Analyzing…" : d.analysis ? "Re-analyze" : "Analyze"}
              </button>
              <button className="ghost small danger" onClick={() => remove(d.id)}>
                delete
              </button>
            </div>
          </div>

          {d.analysis && (
            <div style={{ marginTop: 10 }}>
              <h3>Lessons</h3>
              <pre className="stream">{d.analysis}</pre>
            </div>
          )}

          <details style={{ marginTop: 10 }}>
            <summary style={{ cursor: "pointer", color: "var(--accent)" }}>
              Extracted text ({d.extracted_text.length} chars)
            </summary>
            <pre className="stream">{d.extracted_text || "(empty)"}</pre>
          </details>
        </div>
      ))}
    </div>
  );
}
