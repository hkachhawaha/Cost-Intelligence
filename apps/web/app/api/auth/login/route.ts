import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const { token, user } = await request.json();
    if (!token) {
      return NextResponse.json({ error: "Token is required" }, { status: 400 });
    }

    const cookieName = "sb-cost-intelligence-auth-token";
    const cookieValue = JSON.stringify({ access_token: token, user });

    const response = NextResponse.json({ ok: true });
    response.cookies.set(cookieName, cookieValue, {
      path: "/",
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 7, // 1 week
    });

    return response;
  } catch (e) {
    return NextResponse.json({ error: "Invalid request payload" }, { status: 400 });
  }
}
