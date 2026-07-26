import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emits a minimal standalone server bundle; keeps future production images small.
  output: "standalone",
};

export default nextConfig;
