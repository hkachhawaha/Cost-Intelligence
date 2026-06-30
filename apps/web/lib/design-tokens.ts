// Single source for Terzo tokens (mirrors the approved prototype). Colors map to
// CSS vars consumed by tailwind.config + the shadcn theme (§9.1 — no deviations).
export const terzoTokens = {
  brand: { primary: "var(--terzo-primary)", primaryFg: "var(--terzo-primary-fg)" },
  semantic: {
    savings: "var(--terzo-savings)",
    recovery: "var(--terzo-recovery)",
    control: "var(--terzo-control)",
    danger: "var(--terzo-danger)",
  },
  surface: { base: "var(--terzo-surface)", raised: "var(--terzo-surface-raised)" },
} as const;
