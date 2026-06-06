/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Server-side proxy for API calls.
    // API_URL is a server-only env var; on Railway set it to the backend's
    // internal private URL (e.g. https://backend.railway.internal) or public
    // URL.  Falls back to NEXT_PUBLIC_API_URL then localhost.
    const apiBase =
      process.env.API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";

    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
