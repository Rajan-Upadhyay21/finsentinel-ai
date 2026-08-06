import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinSentinel AI",
  description: "Multi-agent banking intelligence operations center",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
