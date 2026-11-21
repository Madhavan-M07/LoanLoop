import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-900">Page not found</p>
      <Link href="/" className="mt-2 inline-block text-sm font-medium text-indigo-700 hover:underline">
        Back to start
      </Link>
    </div>
  );
}
