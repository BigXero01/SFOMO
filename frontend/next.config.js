/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Proxy /health directly to the backend — the Route Handler at
    // /api/[...path] covers /api/* but not /health.
    const apiBase =
      process.env.API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";

    return [
      {
        source: "/health",
        destination: `${apiBase}/health`,
      },
    ];
  },
};

module.exports = nextConfig;
