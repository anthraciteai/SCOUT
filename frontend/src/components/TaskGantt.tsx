import { useEffect, useState } from "react";
import { ProposalsApi } from "../api";
import type { TaskPlan, TaskPlanResponse, TaskPlanTask } from "../api";
import { useToast } from "../toast";

/** Slice the Technical Approach + Functional Requirements out of the draft
 * into bite-sized tasks with dependencies, and render as a per-phase Gantt.
 * Refuses to run on a stub draft so the LLM turn is always worth spending. */
export default function TaskGantt({
  proposalId,
  proposalChars,
  proposalSha,
}: {
  proposalId: number;
  proposalChars: number;
  proposalSha: string;
}) {
  const [state, setState] = useState<TaskPlanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const toast = useToast();

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await ProposalsApi.tasks(proposalId);
      setState(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Failed to load task plan");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposalId]);

  async function generate() {
    setBusy(true);
    setError("");
    try {
      await ProposalsApi.generateTasks(proposalId);
      toast("Task plan updated from the current draft.");
      await load();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || "Generation failed";
      setError(msg);
      toast(msg, "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="card spinner">Loading task plan…</div>;
  if (!state) return null;

  const snap = state.snapshot;
  const plan = snap?.plan;
  const draftReady = state.ready;
  const staleAgainstDraft = snap ? snap.proposal_sha !== proposalSha : false;

  return (
    <div className="card">
      <div className="row spread">
        <div>
          <h3 style={{ margin: 0 }}>Technical-approach Gantt</h3>
          <p className="meta" style={{ margin: "4px 0 0" }}>
            Dyno slices the Functional Requirements + Technical Approach out of
            the draft into bite-sized tasks (1-4 weeks each) with dependencies
            so you can see the execution shape at a glance.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button
            onClick={generate}
            disabled={!draftReady || busy}
            title={
              draftReady
                ? "Generate a fresh task plan from the current draft"
                : `Add more meat to the draft first (min ${state.min_chars} chars, you have ${state.current_chars}).`
            }
          >
            {busy
              ? "Slicing…"
              : snap
              ? staleAgainstDraft
                ? "Re-generate (draft changed)"
                : "Re-generate"
              : "Generate task plan"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ color: "var(--red)", marginTop: 10, fontSize: 13 }}>{error}</div>
      )}

      {!draftReady && (
        <ReadinessBar
          current={state.current_chars}
          min={state.min_chars}
        />
      )}

      {snap && plan && (
        <>
          <div className="meta" style={{ marginTop: 12, fontSize: 12 }}>
            Snapshot: {new Date(snap.created_at).toLocaleString()} · from a{" "}
            {snap.proposal_chars.toLocaleString()} char draft
            {staleAgainstDraft && (
              <>
                {" "}
                ·{" "}
                <span
                  className="pill yellow"
                  style={{ padding: "1px 8px", fontSize: 11 }}
                >
                  draft has changed since this plan
                </span>
              </>
            )}
          </div>
          {plan.assumptions && (
            <div
              className="meta"
              style={{
                marginTop: 8,
                padding: "6px 10px",
                borderLeft: "3px solid var(--muted)",
                background: "var(--panel-2)",
                fontStyle: "italic",
                fontSize: 12,
              }}
            >
              Dyno's assumption: {plan.assumptions}
            </div>
          )}
          <PlanGantt plan={plan} />
          {plan.requirements && plan.requirements.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary className="meta" style={{ cursor: "pointer" }}>
                Functional requirements ({plan.requirements.length})
              </summary>
              <ul style={{ margin: "8px 0 0 20px", fontSize: 13 }}>
                {plan.requirements.map((r) => (
                  <li key={r.id}>
                    <strong>{r.id}</strong> — {r.text}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}

      {!snap && draftReady && (
        <div className="meta" style={{ marginTop: 12 }}>
          No plan yet. Click <strong>Generate task plan</strong> to slice the
          current draft.
        </div>
      )}
    </div>
  );
}

function ReadinessBar({ current, min }: { current: number; min: number }) {
  const pct = Math.min(100, Math.round((current / min) * 100));
  return (
    <div style={{ marginTop: 14 }}>
      <div className="meta" style={{ marginBottom: 4, fontSize: 12 }}>
        Draft readiness: {current.toLocaleString()} / {min.toLocaleString()} chars
      </div>
      <div className="match-bar" style={{ height: 8 }}>
        <span
          style={{
            width: `${pct}%`,
            background: pct >= 100 ? "var(--green)" : "var(--amber)",
          }}
        />
      </div>
      <div className="meta" style={{ marginTop: 6, fontSize: 12 }}>
        Come back once the Technical Approach + Functional Requirements
        sections have real substance — slicing a stub wastes an LLM turn.
      </div>
    </div>
  );
}

const OWNER_COLORS: Record<string, string> = {
  pm: "#8a7bff",
  swe: "#5aa9ff",
  se: "#5aa9ff",
  rf_engineer: "#ff7a1a",
  ml_engineer: "#ff9c48",
  hw_engineer: "#ff7a1a",
  systems: "#8a7bff",
  qa: "#35d07f",
  ops: "#35d07f",
  test: "#35d07f",
};

function ownerColor(role?: string) {
  if (!role) return "var(--muted)";
  return OWNER_COLORS[role] || "#c9c1ff";
}

function PlanGantt({ plan }: { plan: TaskPlan }) {
  const phases = plan.phases?.length
    ? plan.phases
    : [{ key: "phase1", label: "Phase I", duration_weeks: 26 }];
  return (
    <div style={{ marginTop: 12 }}>
      {phases.map((ph) => {
        const tasks = (plan.tasks || []).filter((t) => t.phase === ph.key);
        if (!tasks.length) return null;
        const maxEnd = tasks.reduce(
          (m, t) => Math.max(m, (t.start_week || 0) + (t.duration_weeks || 0)),
          ph.duration_weeks || 0
        );
        const weekTicks = Array.from({ length: Math.ceil(maxEnd / 4) + 1 }, (_, i) => i * 4);
        return (
          <div key={ph.key} style={{ marginBottom: 18 }}>
            <div className="row spread" style={{ marginBottom: 6 }}>
              <strong style={{ fontSize: 14 }}>{ph.label}</strong>
              <span className="meta" style={{ fontSize: 12 }}>
                {tasks.length} task{tasks.length === 1 ? "" : "s"} · ~{maxEnd} weeks
              </span>
            </div>
            {/* week axis */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "200px 1fr",
                gap: 8,
                marginBottom: 4,
              }}
            >
              <div />
              <div style={{ position: "relative", height: 16 }}>
                {weekTicks.map((w) => (
                  <div
                    key={w}
                    className="meta"
                    style={{
                      position: "absolute",
                      left: `${(w / maxEnd) * 100}%`,
                      transform: "translateX(-50%)",
                      fontSize: 10,
                    }}
                  >
                    w{w}
                  </div>
                ))}
              </div>
            </div>
            {tasks.map((t) => (
              <GanttRow key={t.id} task={t} maxEnd={maxEnd} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function GanttRow({ task, maxEnd }: { task: TaskPlanTask; maxEnd: number }) {
  const leftPct = ((task.start_week || 0) / maxEnd) * 100;
  const widthPct = ((task.duration_weeks || 1) / maxEnd) * 100;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "200px 1fr",
        gap: 8,
        alignItems: "center",
        padding: "4px 0",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 12.5,
            fontWeight: 600,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={task.title}
        >
          <span className="meta" style={{ marginRight: 4 }}>{task.id}</span>
          {task.title}
        </div>
        <div className="meta" style={{ fontSize: 11 }}>
          {task.owner_role || "—"}
          {task.requirements && task.requirements.length > 0 && (
            <> · {task.requirements.join(", ")}</>
          )}
        </div>
      </div>
      <div
        style={{
          position: "relative",
          height: 22,
          background: "var(--panel-2)",
          borderRadius: 4,
        }}
      >
        <div
          title={`${task.title}\n${task.deliverable || ""}\nwk ${task.start_week} → ${
            task.start_week + task.duration_weeks
          }${task.depends_on?.length ? "\ndeps: " + task.depends_on.join(", ") : ""}`}
          style={{
            position: "absolute",
            top: 3,
            bottom: 3,
            left: `${leftPct}%`,
            width: `${Math.max(widthPct, 1.5)}%`,
            background: ownerColor(task.owner_role),
            borderRadius: 3,
            display: "flex",
            alignItems: "center",
            paddingLeft: 6,
            color: "#0e0a06",
            fontSize: 11,
            fontWeight: 700,
            overflow: "hidden",
          }}
        >
          {task.duration_weeks}w
        </div>
        {(task.depends_on || []).length > 0 && (
          <div
            className="meta"
            style={{
              position: "absolute",
              left: `${leftPct}%`,
              top: -2,
              transform: "translateX(-100%)",
              fontSize: 10,
            }}
          >
            ↖
          </div>
        )}
      </div>
    </div>
  );
}
