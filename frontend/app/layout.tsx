import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "YNAB Insights",
  description: "Self-hosted budgeting dashboard backed by YNAB",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
