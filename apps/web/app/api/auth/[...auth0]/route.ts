import { handleAuth } from "@auth0/nextjs-auth0";

// Provides /api/auth/login, /logout, /callback, /me out of the box.
export const GET = handleAuth();
