/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  async rewrites() {
    const target = (process.env.SERVER_API_URL || "http://api:8000").replace(/\/$/, "");
    return [{ source: "/backend/:path*", destination: `${target}/:path*` }];
  },
};
export default nextConfig;
