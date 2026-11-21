import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError, apiFor, unwrap } from "./api/client";
import type { Principal } from "./api/types";

export const TOKEN_COOKIE = "ll_token";

export async function currentToken(): Promise<string | null> {
  return (await cookies()).get(TOKEN_COOKIE)?.value ?? null;
}

export interface SignedIn {
  token: string;
  me: Principal;
}

/** The signed-in user, or a redirect to the sign-in page. */
export async function requireUser(): Promise<SignedIn> {
  const token = await currentToken();
  if (!token) redirect("/");
  try {
    const me = await unwrap(apiFor(token).GET("/me"));
    return { token, me };
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) redirect("/?expired=1");
    throw e;
  }
}

export function isProcessor(me: Principal): boolean {
  return me.scope === "processor";
}
