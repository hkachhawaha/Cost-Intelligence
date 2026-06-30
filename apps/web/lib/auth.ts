import { getAccessToken, getSession } from "@auth0/nextjs-auth0";

import { DEV_AUTH } from "@/lib/dev";

/** Server-side: the current Auth0 session user (or null). */
export async function currentUser() {
  if (DEV_AUTH) return { name: "Dev User", email: "dev@terzo.local" };
  const session = await getSession();
  return session?.user ?? null;
}

/** Server-side: the raw access token for calling the backend API.
 * Local dev: none — the backend's dev_auth_bypass injects the demo principal. */
export async function accessToken(): Promise<string | undefined> {
  if (DEV_AUTH) return undefined;
  const { accessToken } = await getAccessToken();
  return accessToken;
}
