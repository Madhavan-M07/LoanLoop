import Link from "next/link";
import { redirect } from "next/navigation";

import { DraftActions } from "@/components/DraftActions";
import { RefreshButton } from "@/components/RefreshButton";
import { Badge, EmptyState, ErrorState, PageHeader } from "@/components/ui";
import { apiFor, describeError, unwrap } from "@/lib/api/client";
import type { MessageDraft } from "@/lib/api/types";
import { DRAFT_STATUS_LABEL, formatDateTime } from "@/lib/format";
import { isProcessor, requireUser } from "@/lib/session";

export const dynamic = "force-dynamic";

// O4: borrower requests go out as soon as a human approves them. Nothing is sent without this.
export default async function InboxPage() {
  const { token, me } = await requireUser();
  if (!isProcessor(me)) redirect("/upload");

  let drafts: MessageDraft[];
  try {
    drafts = await unwrap(apiFor(token).GET("/drafts"));
  } catch (e) {
    return <ErrorState message={describeError(e)} retryHref="/inbox" />;
  }

  return (
    <>
      <PageHeader
        title="Approval inbox"
        subtitle="Messages to borrowers. Nothing is sent until a processor approves it."
        actions={<RefreshButton loadedAt={new Date().toISOString()} />}
      />
      {me.via_agent ? (
        <p role="note" className="mb-4 rounded-lg bg-amber-50 px-4 py-2 text-sm text-amber-800">
          You&apos;re signed in as an AI agent ({me.via_agent}). Agents can draft messages but the
          API refuses any approval from them. Try it.
        </p>
      ) : null}
      {drafts.length === 0 ? (
        <EmptyState title="Inbox zero">No borrower messages are waiting for approval.</EmptyState>
      ) : (
        <ul className="space-y-4">
          {drafts.map((d) => (
            <li key={d.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                <Link href={`/loans/${d.loan_id}`} className="font-medium text-indigo-700 hover:underline">
                  {d.loan_id}
                </Link>
                <Badge
                  className={
                    d.status === "send_failed"
                      ? "bg-rose-50 text-rose-800 ring-rose-600/20"
                      : "bg-slate-100 text-slate-700 ring-slate-500/20"
                  }
                >
                  {DRAFT_STATUS_LABEL[d.status]}
                </Badge>
                <span className="text-xs text-slate-500">
                  drafted by {d.created_by} · {formatDateTime(d.created_at)}
                </span>
              </div>
              <p className="mb-4 whitespace-pre-line rounded-lg bg-slate-50 p-3 text-sm text-slate-800">
                {d.body}
              </p>
              <DraftActions draftId={d.id} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
