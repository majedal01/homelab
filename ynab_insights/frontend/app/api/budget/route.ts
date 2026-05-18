import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { BUDGET_COOKIE } from "@/lib/api";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as { budget_id?: unknown } | null;
  const budgetId = body?.budget_id;
  if (typeof budgetId !== "string" || !budgetId) {
    return NextResponse.json({ error: "budget_id required" }, { status: 400 });
  }
  (await cookies()).set(BUDGET_COOKIE, budgetId, {
    httpOnly: false,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
  return NextResponse.json({ ok: true });
}
