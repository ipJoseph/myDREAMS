import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Allow MLS photos from CDN and local API
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.cloudfront.net",
      },
      {
        protocol: "https",
        hostname: "api.wncmountain.homes",
      },
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
  },
  // API proxy to avoid CORS issues in development
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
    return [
      {
        source: "/api/public/:path*",
        destination: `${apiUrl}/api/public/:path*`,
      },
    ];
  },
};

export default nextConfig;
