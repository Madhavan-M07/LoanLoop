import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { signOut } from "@/app/actions";
import { demoUser } from "@/lib/demoUsers";
import { currentToken } from "@/lib/session";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "LoanLoop",
  description: "Loan file processing: documents in, complete checked file out.",
};

async function Header() {
  const user = demoUser(await currentToken());
  const isBorrower = user?.home === "/upload";
  const links = !user
    ? []
    : isBorrower
      ? [{ href: "/upload", label: "My loan" }]
      : [
          { href: "/loans", label: "Loan queue" },
          { href: "/inbox", label: "Approval inbox" },
        ];

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
        <Link href={user ? user.home : "/"} className="text-base font-semibold text-slate-900">
          LoanLoop
        </Link>
        <nav aria-label="Main" className="flex gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {user ? (
            <>
              <div className="text-right leading-tight">
                <p className="text-sm font-medium text-slate-900">{user.name}</p>
                <p className="text-xs text-slate-500">{user.role}</p>
              </div>
              <form action={signOut}>
                <button
                  type="submit"
                  className="rounded-md px-2.5 py-1.5 text-sm font-medium text-slate-600 ring-1 ring-inset ring-slate-300 hover:bg-slate-50"
                >
                  Switch user
                </button>
              </form>
            </>
          ) : null}
        </div>
      </div>
    </header>
  );
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <Header />
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 pb-8 text-xs text-slate-400">
          Development build · synthetic data only · a human approves every message to a borrower
        </footer>
      </body>
    </html>
  );
}
