import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "colora-neon": "#D5FD50",
      },
    },
  },
  plugins: [],
} satisfies Config;
