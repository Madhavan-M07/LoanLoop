import { signIn } from "@/app/actions";
import { DEMO_USERS } from "@/lib/demoUsers";

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ expired?: string }>;
}) {
  const { expired } = await searchParams;
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in as a demo user</h1>
      <p className="mt-1 text-sm text-slate-600">
        Development only. Each person sees exactly what their role allows, enforced by the API.
      </p>
      {expired ? (
        <p role="alert" className="mt-4 rounded-lg bg-amber-50 px-4 py-2 text-sm text-amber-800">
          Your session ended. Pick a user again.
        </p>
      ) : null}
      <ul className="mt-6 space-y-3">
        {DEMO_USERS.map((u) => (
          <li key={u.token}>
            <form action={signIn}>
              <input type="hidden" name="token" value={u.token} />
              <button
                type="submit"
                className="flex w-full items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white px-5 py-4 text-left shadow-sm hover:border-indigo-300 hover:bg-indigo-50/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
              >
                <span>
                  <span className="block font-medium text-slate-900">{u.name}</span>
                  <span className="block text-sm text-slate-600">{u.role}</span>
                  <span className="mt-1 block text-xs text-slate-500">{u.note}</span>
                </span>
                <span className="mt-1 text-sm font-medium text-indigo-700">Sign in →</span>
              </button>
            </form>
          </li>
        ))}
      </ul>
    </div>
  );
}
