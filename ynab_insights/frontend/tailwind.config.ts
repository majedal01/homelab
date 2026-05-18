import type { Config } from "tailwindcss";
import colors from "tailwindcss/colors";

// Tremor color tokens that Tailwind would otherwise tree-shake out of the
// final stylesheet. Keep this list in sync with the chart palettes we use
// (indigo, emerald, rose). Tremor reads class names at runtime so the
// generator can't infer them from source files.
const tremorSafelist: string[] = [
  ...["indigo", "emerald", "rose", "slate", "amber", "violet", "cyan", "lime"].flatMap((c) => [
    `bg-${c}-50`,
    `bg-${c}-100`,
    `bg-${c}-200`,
    `bg-${c}-300`,
    `bg-${c}-400`,
    `bg-${c}-500`,
    `bg-${c}-600`,
    `bg-${c}-700`,
    `bg-${c}-800`,
    `bg-${c}-900`,
    `text-${c}-500`,
    `text-${c}-600`,
    `text-${c}-700`,
    `text-${c}-400`,
    `text-${c}-300`,
    `border-${c}-500`,
    `border-${c}-400`,
    `ring-${c}-500`,
    `stroke-${c}-500`,
    `stroke-${c}-400`,
    `fill-${c}-500`,
    `fill-${c}-400`,
  ]),
];

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./node_modules/@tremor/**/*.{js,ts,jsx,tsx}",
  ],
  safelist: tremorSafelist,
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: { "2xl": "1280px" },
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        // Tremor design tokens. Aligned with shadcn `slate`; light tokens
        // pull from Tailwind grays, dark tokens from Tailwind slates.
        tremor: {
          brand: {
            faint: colors.indigo[50],
            muted: colors.indigo[200],
            subtle: colors.indigo[400],
            DEFAULT: colors.indigo[500],
            emphasis: colors.indigo[700],
            inverted: colors.white,
          },
          background: {
            muted: colors.slate[50],
            subtle: colors.slate[100],
            DEFAULT: colors.white,
            emphasis: colors.slate[700],
          },
          border: { DEFAULT: colors.slate[200] },
          ring: { DEFAULT: colors.slate[200] },
          content: {
            subtle: colors.slate[400],
            DEFAULT: colors.slate[500],
            emphasis: colors.slate[700],
            strong: colors.slate[900],
            inverted: colors.white,
          },
        },
        "dark-tremor": {
          brand: {
            faint: "#0B1229",
            muted: colors.indigo[950],
            subtle: colors.indigo[800],
            DEFAULT: colors.indigo[500],
            emphasis: colors.indigo[400],
            inverted: colors.indigo[950],
          },
          background: {
            muted: "#131A2B",
            subtle: colors.slate[800],
            DEFAULT: colors.slate[900],
            emphasis: colors.slate[300],
          },
          border: { DEFAULT: colors.slate[800] },
          ring: { DEFAULT: colors.slate[800] },
          content: {
            subtle: colors.slate[600],
            DEFAULT: colors.slate[500],
            emphasis: colors.slate[200],
            strong: colors.slate[50],
            inverted: colors.slate[950],
          },
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        "tremor-small": "0.375rem",
        "tremor-default": "0.5rem",
        "tremor-full": "9999px",
      },
      boxShadow: {
        "tremor-input": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        "tremor-card":
          "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
        "tremor-dropdown":
          "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
        "dark-tremor-input": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        "dark-tremor-card":
          "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
        "dark-tremor-dropdown":
          "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
      },
      fontSize: {
        "tremor-label": ["0.75rem", { lineHeight: "1rem" }],
        "tremor-default": ["0.875rem", { lineHeight: "1.25rem" }],
        "tremor-title": ["1.125rem", { lineHeight: "1.75rem" }],
        "tremor-metric": ["1.875rem", { lineHeight: "2.25rem" }],
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};

export default config;
