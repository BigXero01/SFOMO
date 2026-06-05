import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SFOMO — AI Trading Bot",
  description: "Institutional-style crypto asset management via multi-agent AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
