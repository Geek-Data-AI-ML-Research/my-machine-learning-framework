/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./public/index.html", "./public/app.js"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Light Studio surfaces (names kept so app.js classes stay stable)
        ink: {
          950: "#f7f7f8",
          900: "#ffffff",
          800: "#f1f1f3",
          700: "#e4e4e7",
          600: "#d4d4d8",
        },
        mist: {
          100: "#fafafa",
          200: "#27272a",
          300: "#3f3f46",
          400: "#52525b",
          500: "#71717a",
        },
        signal: {
          DEFAULT: "#18181b",
          muted: "#52525b",
          ok: "#1a7f37",
          warn: "#9a6700",
          bad: "#cf222e",
        },
      },
      fontFamily: {
        sans: [
          "IBM Plex Sans",
          "ui-sans-serif",
          "system-ui",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "IBM Plex Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      maxWidth: {
        studio: "72rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(24, 24, 27, 0.04), 0 8px 24px rgba(24, 24, 27, 0.04)",
      },
    },
  },
  plugins: [],
};
