export const config = {
  apiBase: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1",
  queryStaleTimeMs: 60_000, // memory-backed data; brief client cache
  dashboardStreamTimeoutMs: 5_000, // soft budget aligned to the <5s NFR
  modulesV1: [
    "dashboard",
    "assessment",
    "spend",
    "contracts",
    "renewals",
    "recovery",
    "data-quality",
  ],
} as const;
