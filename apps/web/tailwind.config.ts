import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0b0d10",
        surface: "#14171c",
        border: "#20242b",
        accent: "#5b8def",
        muted: "#8a92a1",
      },
    },
  },
  plugins: [],
};

export default config;
