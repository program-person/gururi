import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    turbopackFileSystemCacheForDev: false,
  },
  async rewrites() {
    // ローカル開発でローカルbackendを使う場合は .env.local に
    // API_PROXY_TARGET=http://localhost:8000 を設定する
    const target =
      process.env.API_PROXY_TARGET ?? "https://gururi-production.up.railway.app";
    return [
      {
        source: "/api/:path*",
        destination: `${target}/:path*`,
      },
    ];
  },
};

export default nextConfig;
