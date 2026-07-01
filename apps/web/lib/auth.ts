import { cookies } from "next/headers";

import { DEV_AUTH } from "@/lib/dev";

/** Server-side: the current Supabase session user (or null). */
export async function currentUser() {
  if (DEV_AUTH) return { name: "Dev User", email: "dev@terzo.local" };
  const cookieStore = cookies();
  const supabaseCookie = cookieStore.getAll().find(
    (c) => c.name.startsWith("sb-") && c.name.endsWith("-auth-token")
  );
  if (supabaseCookie) {
    try {
      const data = JSON.parse(supabaseCookie.value);
      return data.user || null;
    } catch {
      return null;
    }
  }
  return null;
}

/** Server-side: the raw access token for calling the backend API.
 * Local dev: none — the backend's dev_auth_bypass injects the demo principal. */
export async function accessToken(): Promise<string | undefined> {
  if (DEV_AUTH) return undefined;
  const cookieStore = cookies();
  const supabaseCookie = cookieStore.getAll().find(
    (c) => c.name.startsWith("sb-") && c.name.endsWith("-auth-token")
  );
  if (supabaseCookie) {
    try {
      const data = JSON.parse(supabaseCookie.value);
      return data.access_token || undefined;
    } catch {
      return undefined;
    }
  }
  return undefined;
}
