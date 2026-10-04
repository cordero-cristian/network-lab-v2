import type { ExecutionStage } from "../api/types";
import { formatDuration, formatTime, titleCase } from "../format";
import { EmptyState } from "./AsyncSection";

const marker: Record<ExecutionStage["status"], string> = { completed: "✓", running: "•", failed: "×", not_reached: "–", unknown: "?" };

export function WorkflowTimeline({ stages }: { stages: ExecutionStage[] }) {
  if (!stages.length) return <EmptyState source="Temporal history">No exact durable activity boundaries were returned for this execution.</EmptyState>;
  return (
    <ol className="timeline" aria-label="Exact workflow history">
      {stages.map((stage) => (
        <li className={`timeline__stage timeline__stage--${stage.status}`} key={`${stage.sequence}:${stage.key}`}>
          <span className="timeline__marker" aria-hidden="true">{marker[stage.status]}</span>
          <div className="timeline__main">
            <div className="timeline__title"><strong>{stage.label || "Unknown stage"}</strong><span>{titleCase(stage.status)}</span></div>
            <p className="mono muted">{stage.key}{stage.attempts ? ` · attempt ${stage.attempts}` : ""}</p>
            {stage.status === "failed" && <div className="failure-inline" role="alert"><strong>{stage.failure_category ?? "Stage failed"}</strong><p>{stage.failure_message ?? "No additional safe failure detail is available."}</p></div>}
          </div>
          <div className="timeline__time"><time dateTime={stage.completed_at ?? stage.started_at ?? stage.scheduled_at ?? undefined}>{formatTime(stage.completed_at ?? stage.started_at ?? stage.scheduled_at)}</time><span>{formatDuration(stage.duration_ms)}</span></div>
        </li>
      ))}
    </ol>
  );
}
