/** @type {import('next').NextConfig} */

// Backend URL — set API_BASE_URL as a server-side (non-public) env var in Vercel.
// Falls back to localhost for local dev. Never exposed in the client bundle.
const API_BASE_URL = process.env.API_BASE_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_BASE_URL}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
