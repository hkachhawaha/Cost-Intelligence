import type { Config } from "tailwindcss";

// Terzo Design System over shadcn/ui (§9.1). Semantic colors map to the HSL CSS
// vars defined in globals.css; arbitrary `hsl(var(--terzo-*))` classes resolve
// directly. No off-palette colors — Terzo tokens are the only color source.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        border: "hsl(var(--border))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        brand: { DEFAULT: "#4f46e5", fg: "#ffffff" },
      },
      borderRadius: { DEFAULT: "var(--radius)" },
    },
  },
  plugins: [],
};

export default config;
