/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  // Same-origin API proxy: browsers talk only to this site's domain and
  // Vercel's edge forwards to the backend. Exists because some ISPs (notably
  // in India) refuse DNS for *.up.railway.app — clients never need to resolve
  // the backend host themselves.
  async rewrites() {
    const backend =
      process.env.BACKEND_ORIGIN ||
      "https://callsense-production-d0b3.up.railway.app";
    return [{ source: "/api/backend/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
