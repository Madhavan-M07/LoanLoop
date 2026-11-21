"use client";

import { useActionState } from "react";

import { decideDraft, type ActionResult } from "@/app/actions";

/** Explicit approve / reject. The backend enforces that only a human processor can do this. */
export function DraftActions({ draftId }: { draftId: string }) {
  const [result, action, pending] = useActionState<ActionResult | null, FormData>(
    decideDraft,
    null,
  );

  return (
    <form action={action} className="flex flex-wrap items-center gap-3">
      <input type="hidden" name="draftId" value={draftId} />
      <button
        type="submit"
        name="decision"
        value="approve"
        disabled={pending}
        className="rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:opacity-50"
      >
        {pending ? "Working…" : "Approve & send"}
      </button>
      <button
        type="submit"
        name="decision"
        value="reject"
        disabled={pending}
        className="rounded-lg bg-white px-3.5 py-2 text-sm font-semibold text-slate-700 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500 disabled:opacity-50"
      >
        Reject
      </button>
      {result ? (
        <p
          role="status"
          className={`text-sm ${result.ok ? "text-emerald-700" : "text-rose-700"}`}
        >
          {result.message}
        </p>
      ) : null}
    </form>
  );
}
