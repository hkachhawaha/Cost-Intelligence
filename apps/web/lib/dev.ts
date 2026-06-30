// Local end-to-end testing flag. When NEXT_PUBLIC_DEV_AUTH=1 the app skips Auth0 entirely:
// the middleware passes through, server fetches attach no bearer token, and the backend's
// matching dev_auth_bypass injects a fixed demo principal. NEVER set this in production.
export const DEV_AUTH = process.env.NEXT_PUBLIC_DEV_AUTH === "1";
