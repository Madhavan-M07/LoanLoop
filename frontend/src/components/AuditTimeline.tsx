import { describeChange, formatDateTime, humanize } from "@/lib/format";
import type { AuditEvent } from "@/lib/api/types";

export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-600">No activity recorded yet.</p>;
  }
  // Newest first: the processor usually wants "what just happened".
  const newest = [...events].reverse();
  return (
    <ol className="space-y-3">
      {newest.map((e, i) => {
        const changes = describeChange(e.before, e.after);
        return (
          <li key={`${e.at}-${i}`} className="flex gap-3 text-sm">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-slate-300" aria-hidden />
            <div className="min-w-0">
              <p className="text-slate-900">
                <span className="font-medium">{humanize(e.action)}</span>
                <span className="text-slate-500"> · {e.actor}</span>
              </p>
              {changes.map((c) => (
                <p key={c} className="text-xs font-medium text-indigo-700">
                  {c}
                </p>
              ))}
              {e.detail ? <p className="truncate text-xs text-slate-500">{e.detail}</p> : null}
              <p className="text-xs text-slate-400">{formatDateTime(e.at)}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
