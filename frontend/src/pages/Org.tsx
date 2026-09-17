import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { OrgApi } from "../api";
import type { OrgCompany, SbirWorkspace } from "../types";
import { useAuth } from "../auth";
import { useToast } from "../toast";

export default function Org() {
  const { user } = useAuth();
  const [co, setCo] = useState<OrgCompany | null>(null);
  const [sbirs, setSbirs] = useState<SbirWorkspace[]>([]);
  const [mission, setMission] = useState("");
  const [products, setProducts] = useState("");
  const toast = useToast();

  async function load() {
    const [c, s] = await Promise.all([OrgApi.company(), OrgApi.sbirs()]);
    setCo(c);
    setMission(c.mission);
    setProducts(c.products);
    setSbirs(s);
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
        products are federated. Personal drafts stay under your user folder.
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
        <h2 style={{ marginTop: 0 }}>People in {co.company_id}</h2>
        <p className="meta">From companies/{co.company_id}/employees.txt — complementary stacks for a bid.</p>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Skills</th>
              <th>SBIRs</th>
            </tr>
          </thead>
          <tbody>
            {co.employees.map((e) => (
              <tr key={e.user_id}>
                <td>
                  <strong>{e.display_name}</strong>
                  <div className="meta">{e.user_id}</div>
                </td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    {e.skills.map((s) => (
                      <span className="tag" key={s}>
                        {s}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="meta">{e.sbirs.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Federated SBIRs</h2>
        <p className="meta">
          Union of your sbir.txt and group capture/sbir.txt. Cached council/Flint skip the LLM.
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
              {s.has_shared_proposal && <span className="pill">shared draft</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
