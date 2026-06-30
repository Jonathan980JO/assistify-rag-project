import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  basePath: "/frontend",
  trailingSlash: true,
  turbopack: {
    root: __dirname,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    if (process.env.NODE_ENV === "production") return [];
    const backend = "http://127.0.0.1:7001";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/conversations/:path*", destination: `${backend}/conversations/:path*` },
      { source: "/conversations", destination: `${backend}/conversations` },
      { source: "/arabic/:path*", destination: `${backend}/arabic/:path*` },
      { source: "/tts", destination: `${backend}/tts` },
      { source: "/ws", destination: `${backend}/ws` },
      { source: "/ws/guest", destination: `${backend}/ws/guest` },
      { source: "/api/public/:path*", destination: `${backend}/api/public/:path*` },
      { source: "/api/guest/:path*", destination: `${backend}/api/guest/:path*` },
    ];
  },
};

export default nextConfig;
