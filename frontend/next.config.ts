import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Separate build folders let a second instance (e.g. an automated browser check) run next to
  // your own `npm run dev` without the two overwriting each other's build output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
};

export default nextConfig;
