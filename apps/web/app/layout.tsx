import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI-quant",
  description:
    "Cited AI research dossiers for UK and US public-market investors.",
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
