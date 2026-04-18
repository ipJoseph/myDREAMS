import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Allow MLS photos from local API and CloudFront (Navica)
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.cloudfront.net",
      },
      {
        protocol: "https",
        hostname: "media.mlsgrid.com",
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
      // /api/user/* is handled by src/app/api/user/[...path]/route.ts
      // which adds auth headers before proxying to Flask
    ];
  },
};

export default nextConfig;
