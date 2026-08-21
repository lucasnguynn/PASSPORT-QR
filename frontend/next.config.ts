import type { NextConfig } from "next";
import withPWAInit from "next-pwa";

const withPWA = withPWAInit({ dest: "public", disable: process.env.NODE_ENV === "development" });
const config: NextConfig = {
  output: "standalone",
  async headers() {
    return [{ source: "/(.*)", headers: [{ key: "Content-Security-Policy", value: "default-src 'self'; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self' https:; style-src 'self' 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com" }] }, { source: "/scan", headers: [
      { key: "Permissions-Policy", value: "camera=(self)" },
      { key: "Feature-Policy", value: "camera 'self'" },
    ] }];
  },
};
export default withPWA(config);
