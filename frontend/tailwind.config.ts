import type { Config } from "tailwindcss";

// Tremor color tokens that Tailwind would otherwise tree-shake out of the
// final stylesheet. Keep this list in sync with the chart palettes we use
// (indigo, emerald, rose). Tremor reads class names at runtime so the
// generator can't infer them from source files.
const tremorSafelist: string[] = [
  ...["indigo", "emerald", "rose", "slate", "amber"].flatMap((c) => [
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
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
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
  plugins: [require("tailwindcss-animate")],
};

export default config;
