import { withMiddlewareAuthRequired } from "@auth0/nextjs-auth0/edge";
import { NextResponse } from "next/server";

// Protect every route except the login page, Auth0 handler, and static assets.
// Local dev (NEXT_PUBLIC_DEV_AUTH=1): skip auth entirely so the whole flow is clickable
// without an Auth0 tenant. NEVER enable that flag in production.
const devAuth = process.env.NEXT_PUBLIC_DEV_AUTH === "1";

export default devAuth ? () => NextResponse.next() : withMiddlewareAuthRequired();

export const config = {
  matcher: ["/((?!api/auth|login|_next/static|_next/image|favicon.ico).*)"],
};
