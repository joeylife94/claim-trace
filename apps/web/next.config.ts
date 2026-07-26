import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emits a minimal standalone server bundle; keeps future production images small.
  output: "standalone",
  experimental: {
    // Uploads travel through a server action, whose default body limit is 1 MB.
    // Keep this at or above the API's UPLOAD_MAX_BYTES so the backend, not Next,
    // is what rejects an oversized file - with a proper error code.
    serverActions: { bodySizeLimit: "24mb" },
  },
};

export default nextConfig;
