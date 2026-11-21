"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { apiFor, describeError, unwrap } from "@/lib/api/client";
import { DEMO_USERS, demoUser } from "@/lib/demoUsers";
import { TOKEN_COOKIE, currentToken } from "@/lib/session";

export interface ActionResult {
  ok: boolean;
  message: string;
}

export async function signIn(formData: FormData): Promise<void> {
  const token = String(formData.get("token") ?? "");
  const user = demoUser(token);
  if (!user) redirect("/"); // only the known demo identities, never arbitrary input
  (await cookies()).set(TOKEN_COOKIE, user.token, {
    httpOnly: true, // page scripts can't read it
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  redirect(user.home);
}

export async function signOut(): Promise<void> {
  (await cookies()).delete(TOKEN_COOKIE);
  redirect("/");
}

async function tokenOrFail(): Promise<string | null> {
  const token = await currentToken();
  return token && DEMO_USERS.some((u) => u.token === token) ? token : null;
}

export async function decideDraft(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const token = await tokenOrFail();
  if (!token) return { ok: false, message: "You're signed out. Sign in again." };
  const draftId = String(formData.get("draftId") ?? "");
  const decision = String(formData.get("decision") ?? "");
  if (!draftId || (decision !== "approve" && decision !== "reject")) {
    return { ok: false, message: "Unknown action." };
  }
  try {
    const params = { params: { path: { draft_id: draftId } } };
    const api = apiFor(token);
    const draft = await unwrap(
      decision === "approve"
        ? api.POST("/drafts/{draft_id}/approve", params)
        : api.POST("/drafts/{draft_id}/reject", params),
    );
    revalidatePath("/", "layout");
    if (decision === "reject") return { ok: true, message: "Rejected. Nothing was sent." };
    return draft.status === "sent"
      ? { ok: true, message: "Approved and sent to the borrower." }
      : { ok: false, message: "Approved, but sending failed. It's back in the inbox to retry." };
  } catch (e) {
    return { ok: false, message: describeError(e) };
  }
}

export async function uploadDocument(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const token = await tokenOrFail();
  if (!token) return { ok: false, message: "You're signed out. Sign in again." };
  const loanId = String(formData.get("loanId") ?? "");
  const filename = String(formData.get("filename") ?? "").trim();
  const text = String(formData.get("text") ?? "");
  if (!loanId || !filename || !text.trim()) {
    return { ok: false, message: "Add a file name and some document text first." };
  }
  try {
    const doc = await unwrap(
      apiFor(token).POST("/loans/{loan_id}/documents", {
        params: { path: { loan_id: loanId } },
        body: { filename, text },
      }),
    );
    revalidatePath("/", "layout");
    const what = doc.doc_type === "unknown" ? "an unrecognized document" : doc.doc_type;
    if (doc.status === "extracted") return { ok: true, message: `Received and read as ${what}.` };
    if (doc.status === "needs_review")
      return { ok: true, message: `Received as ${what}. A processor will review it.` };
    return { ok: false, message: `The document was rejected: ${doc.review_reasons.join("; ")}` };
  } catch (e) {
    return { ok: false, message: describeError(e) };
  }
}
