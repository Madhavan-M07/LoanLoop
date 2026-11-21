"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

/** Data is fetched when the page renders; this shows how fresh it is and reloads it. */
export function RefreshButton({ loadedAt }: { loadedAt: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  // UTC like every other timestamp on the page (and identical on server and client render).
  const time = new Date(loadedAt).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  });
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span>Updated {time}</span>
      <button
        type="button"
        onClick={() => start(() => router.refresh())}
        disabled={pending}
        className="rounded-md px-2 py-1 font-medium text-indigo-700 ring-1 ring-inset ring-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
      >
        {pending ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );
}
