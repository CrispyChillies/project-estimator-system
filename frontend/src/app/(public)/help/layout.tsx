import Link from "next/link";

import { PublicHeader } from "@/components/public-header";
import { HELP_PAGES } from "@/lib/help";

export default function HelpLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <PublicHeader />
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-8 md:grid-cols-[220px_1fr]">
        <aside aria-label="Guides" className="text-sm">
          <ul className="space-y-1 md:sticky md:top-20">
            <li>
              <Link href="/help" className="font-medium hover:underline">All guides</Link>
            </li>
            {HELP_PAGES.map((p) => (
              <li key={p.slug}>
                <Link href={`/help/${p.slug}`} className="text-muted-foreground hover:text-foreground hover:underline">
                  {p.title}
                </Link>
              </li>
            ))}
          </ul>
        </aside>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
