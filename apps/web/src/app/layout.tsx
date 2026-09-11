import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Spy — Search Intelligence",
  description: "SEO, AEO and GEO intelligence in one platform.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
