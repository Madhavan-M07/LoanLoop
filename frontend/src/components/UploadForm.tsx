"use client";

import { useActionState, useState } from "react";

import { uploadDocument, type ActionResult } from "@/app/actions";
import {
  SAMPLE_LABELS,
  buildSample,
  sampleFilename,
  todayIso,
  type SampleKind,
} from "@/lib/samples";

/** Borrower upload simulator: build a SYNTHETIC document, edit it if you like, upload it. */
export function UploadForm({ loanId, borrowerName }: { loanId: string; borrowerName: string }) {
  const [kind, setKind] = useState<SampleKind>("paystub");
  const [date, setDate] = useState(todayIso());
  const [text, setText] = useState(() =>
    buildSample("paystub", { name: borrowerName, date: todayIso(), taxYear: 2025 }),
  );
  const [result, action, pending] = useActionState<ActionResult | null, FormData>(
    uploadDocument,
    null,
  );

  function regenerate(nextKind: SampleKind, nextDate: string) {
    setText(buildSample(nextKind, { name: borrowerName, date: nextDate, taxYear: 2025 }));
  }

  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="loanId" value={loanId} />
      <input type="hidden" name="filename" value={sampleFilename(kind)} />
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="font-medium text-slate-700">Document</span>
          <select
            value={kind}
            onChange={(e) => {
              const k = e.target.value as SampleKind;
              setKind(k);
              regenerate(k, date);
            }}
            className="mt-1 block w-full rounded-lg border-0 py-2 pl-3 pr-8 text-slate-900 ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-indigo-600"
          >
            {(Object.keys(SAMPLE_LABELS) as SampleKind[]).map((k) => (
              <option key={k} value={k}>
                {SAMPLE_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="font-medium text-slate-700">Pay / statement date</span>
          <input
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              regenerate(kind, e.target.value);
            }}
            className="mt-1 block w-full rounded-lg border-0 px-3 py-2 text-slate-900 ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-indigo-600"
          />
          <span className="mt-1 block text-xs text-slate-500">
            Pick an old date to see an &quot;expired document&quot; request.
          </span>
        </label>
      </div>
      <label className="block text-sm">
        <span className="font-medium text-slate-700">Document text (synthetic, editable)</span>
        <textarea
          name="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={11}
          spellCheck={false}
          className="mt-1 block w-full rounded-lg border-0 px-3 py-2 font-mono text-xs text-slate-900 ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-indigo-600"
        />
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:opacity-50"
        >
          {pending ? "Uploading…" : "Upload document"}
        </button>
        {result ? (
          <p role="status" className={`text-sm ${result.ok ? "text-emerald-700" : "text-rose-700"}`}>
            {result.message}
          </p>
        ) : null}
      </div>
    </form>
  );
}
