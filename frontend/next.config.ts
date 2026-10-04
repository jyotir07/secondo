import type { NextConfig } from "next";

// The browser only ever talks to this origin; Next forwards /api/* to FastAPI. That keeps the
// backend address out of client bundles and avoids CORS in local and hosted setups alike.
const backendUrl = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
