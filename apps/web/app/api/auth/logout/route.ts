import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const cookieName = "sb-cost-intelligence-auth-token";
  const url = request.nextUrl.clone();
  url.pathname = "/login";

  const response = NextResponse.redirect(url);
  response.cookies.set(cookieName, "", {
    path: "/",
    maxAge: 0,
  });
  return response;
}
