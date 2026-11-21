import Link from "next/link";
import { redirect } from "next/navigation";

import { AuditTimeline } from "@/components/AuditTimeline";
import { DraftActions } from "@/components/DraftActions";
import { ExtractedFields } from "@/components/ExtractedFields";
import { RefreshButton } from "@/components/RefreshButton";
import {
  Card,
  DocStatusBadge,
  ErrorState,
  PageHeader,
  SeverityBadge,
  StageBadge,
} from "@/components/ui";
import { ApiError, apiFor, describeError, unwrap } from "@/lib/api/client";
import type { AuditEvent, LoanFile } from "@/lib/api/types";
import { docTypeLabel, formatDateTime, percent } from "@/lib/format";
import { isProcessor, requireUser } from "@/lib/session";

export const dynamic = "force-dynamic";

// O1/O3: everything about one file on one screen, with the evidence behind each AI value,
// so the processor checks instead of re-reading every document.
export default async function LoanFilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { token, me } = await requireUser();
  if (!isProcessor(me)) redirect("/upload");

  let file: LoanFile;
  let audit: AuditEvent[];
  try {
    const api = apiFor(token);
    [file, audit] = await Promise.all([
      unwrap(api.GET("/loans/{loan_id}", { params: { path: { loan_id: id } } })),
      unwrap(api.GET("/audit", { params: { query: { loan_id: id } } })),
    ]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return <ErrorState message={`Loan ${id} doesn't exist or isn't in your organization.`} retryHref="/loans" />;
    }
    return <ErrorState message={describeError(e)} retryHref={`/loans/${id}`} />;
  }

  const { loan, documents, rule_results, pending_drafts } = file;
  const received = new Set(documents.filter((d) => d.status !== "rejected").map((d) => d.doc_type));
  const issues = rule_results.filter((r) => r.severity !== "pass");
  const passes = rule_results.filter((r) => r.severity === "pass");

  return (
    <>
      <p className="mb-2 text-sm">
        <Link href="/loans" className="text-indigo-700 hover:underline">← Loan queue</Link>
      </p>
      <PageHeader
        title={`${loan.borrower_name} · ${loan.id}`}
        subtitle={<>Loan officer {loan.loan_officer} · monthly debts ${loan.monthly_debts}</>}
        actions={
          <>
            <StageBadge stage={loan.stage} />
            <RefreshButton loadedAt={new Date().toISOString()} />
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Required documents">
            <ul className="flex flex-wrap gap-2">
              {loan.required_docs.map((d) => (
                <li
                  key={d}
                  className={`rounded-lg px-3 py-1.5 text-sm ring-1 ring-inset ${received.has(d) ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20" : "bg-slate-50 text-slate-600 ring-slate-300"}`}
                >
                  {received.has(d) ? "✓ " : "○ "}
                  {docTypeLabel(d)}
                </li>
              ))}
            </ul>
          </Card>

          <Card title={`Checks (${issues.length} need attention)`}>
            {rule_results.length === 0 ? (
              <p className="text-sm text-slate-600">No checks yet: they run when documents arrive.</p>
            ) : (
              <ul className="space-y-3">
                {[...issues, ...passes].map((r, i) => (
                  <li key={`${r.code}-${i}`} className="flex items-start gap-3 text-sm">
                    <SeverityBadge severity={r.severity} />
                    <div>
                      <p className="text-slate-900">{r.message}</p>
                      {r.borrower_action ? (
                        <p className="text-xs text-slate-500">Ask borrower: {r.borrower_action}</p>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title={`Documents (${documents.length})`}>
            {documents.length === 0 ? (
              <p className="text-sm text-slate-600">The borrower hasn&apos;t uploaded anything yet.</p>
            ) : (
              <div className="space-y-6">
                {documents.map((d) => (
                  <article key={d.id} className="border-b border-slate-100 pb-6 last:border-0 last:pb-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <h3 className="font-medium text-slate-900">{docTypeLabel(d.doc_type)}</h3>
                      <DocStatusBadge status={d.status} />
                      {d.classification ? (
                        <span
                          className={`text-xs ${d.classification.confidence < 0.8 ? "font-medium text-amber-700" : "text-slate-500"}`}
                          title={d.classification.reason}
                        >
                          AI confidence {percent(d.classification.confidence)}
                        </span>
                      ) : null}
                      <span className="ml-auto text-xs text-slate-400">
                        {d.filename} · {formatDateTime(d.uploaded_at)}
                      </span>
                    </div>
                    {d.review_reasons.length > 0 ? (
                      <ul className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                        {d.review_reasons.map((reason) => (
                          <li key={reason}>⚠ {reason}</li>
                        ))}
                      </ul>
                    ) : null}
                    {d.fields ? (
                      <ExtractedFields fields={d.fields} />
                    ) : (
                      <p className="text-sm text-slate-600">No fields extracted.</p>
                    )}
                  </article>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Messages waiting for approval">
            {pending_drafts.length === 0 ? (
              <p className="text-sm text-slate-600">Nothing to approve for this file.</p>
            ) : (
              <ul className="space-y-4">
                {pending_drafts.map((d) => (
                  <li key={d.id} className="space-y-3">
                    <p className="whitespace-pre-line rounded-lg bg-slate-50 p-3 text-sm text-slate-800">
                      {d.body}
                    </p>
                    <DraftActions draftId={d.id} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Activity">
            <AuditTimeline events={audit} />
          </Card>
        </div>
      </div>
    </>
  );
}
