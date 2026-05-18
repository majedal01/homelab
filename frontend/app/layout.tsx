import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { Nav } from "@/components/nav";
import { Toaster } from "@/components/ui/sonner";
import { apiFetch, getSelectedBudgetId } from "@/lib/api";
import type { BudgetResponse } from "@/lib/api-types";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "YNAB Insights",
  description: "Self-hosted budgeting dashboard backed by YNAB",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  let budgets: BudgetResponse[] = [];
  try {
    budgets = await apiFetch<BudgetResponse[]>("/budgets");
  } catch {
    // Backend unreachable during build/SSR shouldn't crash the shell.
    budgets = [];
  }
  const selectedBudgetId = await getSelectedBudgetId(budgets);

  return (
    <html lang="en" suppressHydrationWarning className={inter.variable}>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <Nav budgets={budgets} selectedBudgetId={selectedBudgetId} />
          <main className="container py-6">{children}</main>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
