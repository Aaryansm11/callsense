/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#fafafa",
        card: "#ffffff",
        ink: "#0a0a0a",
        muted: "#6b7280",
        border: "#e5e7eb",
        brand: { DEFAULT: "#4f46e5", soft: "#eef2ff" },
        ok: "#16a34a",
        warn: "#d97706",
        crit: "#dc2626",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06)",
      },
    },
  },
  plugins: [],
};
