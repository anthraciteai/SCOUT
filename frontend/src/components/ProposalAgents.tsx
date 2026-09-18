import { useState } from "react";
import AgentChat from "./AgentChat";
import { AGENTS, COLORS, CONTRIBUTES, ORDER, ROLES, SLICES, type AgentName } from "./agentWorkspace";

export default function ProposalAgents({
  topicId,
  proposalText,
}: {
  topicId: string;
  proposalText: string;
}) {
  const [agent, setAgent] = useState<AgentName>("Flint");
  const spec = AGENTS[agent];
  return (
    <div className="card">
      <div className="row spread">
        <div>
          <h3 style={{ margin: 0 }}>Work the draft with an agent</h3>
          <div className="meta">
            Product voices map that product to this SBIR. They write the sections that are theirs.
          </div>
        </div>
      </div>
      <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap" }}>
        {ORDER.map((name) => (
          <button
            key={name}
            className={agent === name ? "small" : "ghost small"}
            style={
              agent === name
                ? { background: COLORS[name], color: "#04121f" }
                : { borderColor: COLORS[name], color: COLORS[name] }
            }
            onClick={() => setAgent(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <p className="meta" style={{ margin: "8px 0 6px" }}>
        {ROLES[agent]} — {spec.because}
      </p>
      <div className="kv">Reads</div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        {spec.reads.map((id) => (
          <span className="cite-chip" key={id} style={{ cursor: "default" }}>
            {SLICES[id].label}
          </span>
        ))}
      </div>
      <div className="kv">Writes into this draft</div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {spec.contributes.map((id) => (
          <span className="contrib-chip open" key={id} title={CONTRIBUTES[id].hint}>
            {CONTRIBUTES[id].label}
          </span>
        ))}
      </div>
      <AgentChat topicId={topicId} agent={agent} proposalText={proposalText} />
    </div>
  );
}
