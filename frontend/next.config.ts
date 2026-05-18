import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    turbopackFileSystemCacheForDev: false,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "https://gururi-production.up.railway.app/:path*",
      },
    ];
  },
};

export default nextConfig;
