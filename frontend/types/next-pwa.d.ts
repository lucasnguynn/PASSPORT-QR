declare module "next-pwa" {
  import type { NextConfig } from "next";
  export default function withPWAInit(options: { dest: string; disable?: boolean }): (config: NextConfig) => NextConfig;
}
