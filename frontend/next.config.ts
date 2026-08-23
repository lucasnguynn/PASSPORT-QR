import type { NextConfig } from "next";
import withPWAInit from "next-pwa";

const withPWA = withPWAInit({ dest: "public", disable: process.env.NODE_ENV === "development" });
const config: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};
export default withPWA(config);
