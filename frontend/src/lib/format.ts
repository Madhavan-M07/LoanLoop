import type { DocStatus, DraftStatus, LoanStage, Severity } from "./api/types";

export const STAGE_LABEL: Record<LoanStage, string> = {
  collecting_documents: "Collecting documents",
  needs_processor_review: "Needs review",
  file_complete: "File complete",
};

export const STAGE_STYLE: Record<LoanStage, string> = {
  collecting_documents: "bg-amber-50 text-amber-800 ring-amber-600/20",
  needs_processor_review: "bg-rose-50 text-rose-800 ring-rose-600/20",
  file_complete: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  pass: "Pass",
  warn: "Warning",
  fail: "Fail",
};

export const SEVERITY_STYLE: Record<Severity, string> = {
  pass: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  warn: "bg-amber-50 text-amber-800 ring-amber-600/20",
  fail: "bg-rose-50 text-rose-800 ring-rose-600/20",
};

export const DOC_STATUS_LABEL: Record<DocStatus, string> = {
  received: "Received",
  extracted: "Extracted",
  needs_review: "Needs review",
  rejected: "Rejected",
};

export const DOC_STATUS_STYLE: Record<DocStatus, string> = {
  received: "bg-slate-100 text-slate-700 ring-slate-500/20",
  extracted: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  needs_review: "bg-amber-50 text-amber-800 ring-amber-600/20",
  rejected: "bg-rose-50 text-rose-800 ring-rose-600/20",
};

export const DRAFT_STATUS_LABEL: Record<DraftStatus, string> = {
  pending_approval: "Waiting for approval",
  approved: "Approved",
  rejected: "Rejected",
  sent: "Sent",
  send_failed: "Send failed — retry",
};

const DOC_TYPE_LABEL: Record<string, string> = {
  paystub: "Paystub",
  w2: "W-2",
  bank_statement: "Bank statement",
  unknown: "Unknown",
};

export function docTypeLabel(t: string): string {
  return DOC_TYPE_LABEL[t] ?? t;
}

/** "gross_pay" -> "Gross pay" */
export function humanize(key: string): string {
  const s = key.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function daysAgo(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

export function percent(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

/** Renders a value for display. Money and dates stay exactly as the API sent them. */
export function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.map(formatValue).join(", ") : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Audit before/after as readable lines: "Stage: collecting_documents → file_complete". */
export function describeChange(
  before: Record<string, unknown> | null | undefined,
  after: Record<string, unknown> | null | undefined,
): string[] {
  if (!before && !after) return [];
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  return keys
    .filter((k) => formatValue(before?.[k]) !== formatValue(after?.[k]))
    .map((k) => `${humanize(k)}: ${formatValue(before?.[k])} → ${formatValue(after?.[k])}`);
}
