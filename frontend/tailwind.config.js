/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // SCOUT anthracite + ember design tokens (mirrors the CSS variables
        // in index.css so inline var() usages and utilities stay in sync).
        bg: "#0a0b0d",
        bg2: "#0e1013",
        surface: "#14161b",
        surface2: "#1a1d24",
        ink: "#f5f6f8",
        muted: "#a3a9b4",
        faint: "#6f7580",
        ember: "#ff7a1a",
        gold: "#ffc24b",
        davy: "#8a7bff",
        canari: "#35d07f",
        green: "#35d07f",
        amber: "#ffc24b",
        red: "#ff5d5d",
        anthracite: "#4b5563",
        hair: "rgba(255,255,255,0.08)",
        hairstrong: "rgba(255,255,255,0.16)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      backgroundImage: {
        "ember-grad": "linear-gradient(135deg, #ff7a1a 0%, #ffc24b 100%)",
        "card-grad": "linear-gradient(180deg, #14161b, #0e1013)",
        "sidebar-grad":
          "linear-gradient(180deg, rgba(20,22,27,0.9), rgba(10,11,13,0.9))",
      },
      boxShadow: {
        card: "0 20px 50px -20px rgba(0,0,0,0.8)",
        glow: "0 0 0 1px rgba(255,255,255,0.08), 0 24px 60px -24px rgba(255,122,26,0.35)",
        btn: "0 10px 24px -14px rgba(255,122,26,0.6)",
        "btn-hover": "0 14px 30px -14px rgba(255,122,26,0.7)",
        drawer: "-28px 0 70px -30px rgba(0,0,0,0.85)",
      },
      borderRadius: {
        card: "16px",
      },
    },
  },
  plugins: [],
};
