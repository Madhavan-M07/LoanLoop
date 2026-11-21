"use client";

// Last-resort error boundary. Pages handle API errors themselves; this catches the unexpected.
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-5 py-4">
      <p className="text-sm font-medium text-rose-900">Something went wrong on this page.</p>
      <p className="mt-1 text-sm text-rose-800">
        Check that the backend is running on port 8000, then try again.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-3 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-rose-900 ring-1 ring-inset ring-rose-300 hover:bg-rose-100"
      >
        Try again
      </button>
    </div>
  );
}
