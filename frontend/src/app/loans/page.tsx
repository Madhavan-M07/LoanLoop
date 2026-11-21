import Link from "next/link";
import { redirect } from "next/navigation";

import { RefreshButton } from "@/components/RefreshButton";
import { EmptyState, ErrorState, PageHeader, StageBadge } from "@/components/ui";
import { apiFor, describeError, unwrap } from "@/lib/api/client";
import type { LoanSummary } from "@/lib/api/types";
import { daysAgo } from "@/lib/format";
import { isProcessor, requireUser } from "@/lib/session";

export const dynamic = "force-dynamic";

// O1/O5: one place to see which files need the processor, so nothing waits unnoticed.
export default async function LoanQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const { token, me } = await requireUser();
  if (!isProcessor(me)) redirect("/upload");
  const stuckOnly = (await searchParams).view === "stuck";

  let loans: LoanSummary[];
  try {
    const api = apiFor(token);
    loans = await unwrap(stuckOnly ? api.GET("/loans/stuck") : api.GET("/loans"));
  } catch (e) {
    return <ErrorState message={describeError(e)} retryHref="/loans" />;
  }

  const tab = (active: boolean) =>
    `rounded-md px-3 py-1.5 text-sm font-medium ${active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`;

  return (
    <>
      <PageHeader
        title="Loan queue"
        subtitle={`${me.org_id} · ${loans.length} ${stuckOnly ? "stuck " : ""}file${loans.length === 1 ? "" : "s"}`}
        actions={<RefreshButton loadedAt={new Date().toISOString()} />}
      />
      <div className="mb-4 flex gap-2" role="tablist" aria-label="Filter">
        <Link href="/loans" className={tab(!stuckOnly)} aria-current={!stuckOnly ? "page" : undefined}>
          All files
        </Link>
        <Link
          href="/loans?view=stuck"
          className={tab(stuckOnly)}
          aria-current={stuckOnly ? "page" : undefined}
        >
          Stuck (no activity)
        </Link>
      </div>

      {loans.length === 0 ? (
        <EmptyState title={stuckOnly ? "No stuck files" : "No loan files yet"}>
          {stuckOnly ? "Every open file has had recent activity." : "Loan files appear here once created."}
        </EmptyState>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-5 py-3 font-medium">Loan</th>
                <th scope="col" className="px-5 py-3 font-medium">Borrower</th>
                <th scope="col" className="px-5 py-3 font-medium">Stage</th>
                <th scope="col" className="px-5 py-3 font-medium">Last activity</th>
                <th scope="col" className="px-5 py-3 text-right font-medium">Open issues</th>
                <th scope="col" className="px-5 py-3 text-right font-medium">Messages to approve</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loans.map((l) => (
                <tr key={l.loan_id} className="hover:bg-slate-50">
                  <td className="px-5 py-3">
                    <Link href={`/loans/${l.loan_id}`} className="font-medium text-indigo-700 hover:underline">
                      {l.loan_id}
                    </Link>
                  </td>
                  <td className="px-5 py-3 text-slate-900">{l.borrower_name}</td>
                  <td className="px-5 py-3"><StageBadge stage={l.stage} /></td>
                  <td className={`px-5 py-3 ${l.days_since_activity >= 2 ? "font-medium text-amber-700" : "text-slate-600"}`}>
                    {daysAgo(l.days_since_activity)}
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums">{l.open_issues}</td>
                  <td className="px-5 py-3 text-right tabular-nums">
                    {l.pending_drafts > 0 ? (
                      <Link href="/inbox" className="font-medium text-indigo-700 hover:underline">
                        {l.pending_drafts}
                      </Link>
                    ) : (
                      0
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
