import type { Metadata } from "next";

import { Providers } from "@/components/providers";

import "./globals.css";

const index = process.env.ROBOTS_INDEX === "true";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.PUBLIC_APP_URL ?? "http://localhost:3000"),
  title: { default: "Calibr — Project Calibrate UI", template: "%s · Calibr" },
  description:
    "Turn client briefs into reviewable, calibrated software estimates: ranges with provenance, a chat agent that edits the table, and learning from delivered projects.",
  applicationName: "Calibr — Project Calibrate UI",
  robots: index ? { index: true, follow: true } : { index: false, follow: false },
  openGraph: {
    title: "Calibr — Project Calibrate UI",
    description: "Turn client briefs into reviewable, calibrated software estimates.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "Calibr estimate workspace" }],
    type: "website",
  },
  icons: { icon: [{ url: "/favicon.svg", type: "image/svg+xml" }], apple: "/apple-touch-icon.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className="h-full antialiased">
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
