import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Y2K Camera Arbitrage Command Center",
  description: "Real-time deal triage and high-density inventory management system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-black text-slate-100 antialiased`} suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
