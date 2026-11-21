import Link from "next/link";
import type { ReactNode } from "react";

import {
  DOC_STATUS_LABEL,
  DOC_STATUS_STYLE,
  SEVERITY_LABEL,
  SEVERITY_STYLE,
  STAGE_LABEL,
  STAGE_STYLE,
} from "@/lib/format";
import type { DocStatus, LoanStage, Severity } from "@/lib/api/types";

export function Badge({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}
    >
      {children}
    </span>
  );
}

export function StageBadge({ stage }: { stage: LoanStage }) {
  return <Badge className={STAGE_STYLE[stage]}>{STAGE_LABEL[stage]}</Badge>;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge className={SEVERITY_STYLE[severity]}>{SEVERITY_LABEL[severity]}</Badge>;
}

export function DocStatusBadge({ status }: { status: DocStatus }) {
  return <Badge className={DOC_STATUS_STYLE[status]}>{DOC_STATUS_LABEL[status]}</Badge>;
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-slate-600">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
    </div>
  );
}

export function Card({
  title,
  children,
  aside,
}: {
  title?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {title ? (
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {aside}
        </div>
      ) : null}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-900">{title}</p>
      {children ? <div className="mt-1 text-sm text-slate-600">{children}</div> : null}
    </div>
  );
}

export function ErrorState({ message, retryHref }: { message: string; retryHref?: string }) {
  return (
    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-5 py-4">
      <p className="text-sm font-medium text-rose-900">Couldn&apos;t load this page</p>
      <p className="mt-1 text-sm text-rose-800">{message}</p>
      {retryHref ? (
        <Link href={retryHref} className="mt-3 inline-block text-sm font-medium text-rose-900 underline">
          Try again
        </Link>
      ) : null}
    </div>
  );
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-3" aria-busy="true" aria-label="Loading">
      <div className="h-7 w-48 rounded bg-slate-200" />
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-12 rounded-lg bg-slate-100" />
      ))}
    </div>
  );
}
