import type { Config } from "tailwindcss";

// Visual-redesign tokens (see docs/redesign — legal_ai_redesign_pack), ported
// from the pack's CSS custom properties into Tailwind theme colors so every
// component uses ordinary utility classes instead of a second stylesheet.
// Semantics: brand = primary accent, success/warning/danger/violet = status
// colors, ink/muted/line/panel/canvas = the light-content-area palette that
// sits inside the app's existing dark sidebar.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f5f7fb",
        panel: "#ffffff",
        "panel-muted": "#f9fafb",
        ink: "#101828",
        muted: "#667085",
        line: "#e4e7ec",
        brand: { DEFAULT: "#1d4ed8", strong: "#1e40af", soft: "#eff6ff" },
        success: { DEFAULT: "#067647", soft: "#ecfdf3" },
        warning: { DEFAULT: "#b54708", soft: "#fffaeb" },
        danger: { DEFAULT: "#b42318", soft: "#fef3f2" },
        violet: { DEFAULT: "#6941c6", soft: "#f4f3ff" },
      },
      boxShadow: {
        panel: "0 10px 30px rgba(16,24,40,.08)",
      },
      borderRadius: {
        panel: "14px",
      },
    },
  },
  plugins: [],
};

export default config;
