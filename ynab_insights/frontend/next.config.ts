import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for `next start` inside Docker so the server listens on 0.0.0.0
  output: "standalone",
  // Disable image optimization (we don't ship images; saves complexity)
  images: { unoptimized: true },
};

export default nextConfig;
