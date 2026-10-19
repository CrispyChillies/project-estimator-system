import type { Metadata } from "next";
import Link from "next/link";

import { HELP_PAGES } from "@/lib/help";

export const metadata: Metadata = { title: "Help" };

export default function HelpIndex() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Help and guides</h1>
        <p className="text-muted-foreground">How to go from a client brief to a calibrated quote, and how to read the results.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {HELP_PAGES.map((p) => (
          <Link key={p.slug} href={`/help/${p.slug}`} className="rounded-lg border p-4 hover:bg-accent">
            <div className="font-medium">{p.title}</div>
            <div className="text-sm text-muted-foreground">{p.summary}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
