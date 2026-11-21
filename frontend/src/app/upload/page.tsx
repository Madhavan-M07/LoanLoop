import { UploadForm } from "@/components/UploadForm";
import { Card, EmptyState, ErrorState, PageHeader, StageBadge } from "@/components/ui";
import { apiFor, describeError, unwrap } from "@/lib/api/client";
import type { LoanStatus } from "@/lib/api/types";
import { demoUser } from "@/lib/demoUsers";
import { requireUser } from "@/lib/session";

export const dynamic = "force-dynamic";

// O4: the borrower sees exactly what's still missing and can send it right away.
// Simulates the WhatsApp/Telegram channel with SYNTHETIC documents.
export default async function BorrowerPage() {
  const { token, me } = await requireUser();
  if (me.scope !== "borrower" || !me.loan_id) {
    return (
      <EmptyState title="This page is the borrower's view">
        Use &quot;Switch user&quot; and sign in as Priya or John to upload documents.
      </EmptyState>
    );
  }

  let status: LoanStatus;
  try {
    status = await unwrap(
      apiFor(token).GET("/loans/{loan_id}/status", { params: { path: { loan_id: me.loan_id } } }),
    );
  } catch (e) {
    return <ErrorState message={describeError(e)} retryHref="/upload" />;
  }
  const name = demoUser(token)?.name ?? "Borrower";

  return (
    <>
      <PageHeader
        title={`Hi ${name.split(" ")[0]}`}
        subtitle={`Your loan ${status.loan_id}`}
        actions={<StageBadge stage={status.stage} />}
      />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Still needed from you">
            {status.outstanding_items.length === 0 ? (
              <p className="text-sm text-emerald-700">Nothing right now. Thank you!</p>
            ) : (
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-800">
                {status.outstanding_items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Received">
            {status.documents_received.length === 0 ? (
              <p className="text-sm text-slate-600">Nothing yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-slate-800">
                {status.documents_received.map((d, i) => (
                  <li key={`${d}-${i}`}>{d}</li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <div className="lg:col-span-3">
          <Card title="Send a document (simulator)">
            <UploadForm loanId={status.loan_id} borrowerName={name} />
          </Card>
        </div>
      </div>
    </>
  );
}
