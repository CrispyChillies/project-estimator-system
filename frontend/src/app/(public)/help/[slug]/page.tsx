import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { HELP_PAGES } from "@/lib/help";

export function generateStaticParams() {
  return HELP_PAGES.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  return { title: HELP_PAGES.find((p) => p.slug === slug)?.title ?? "Help" };
}

export default async function HelpPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const page = HELP_PAGES.find((p) => p.slug === slug);
  if (!page) notFound();
  const Body = page.Body;
  return (
    <article className="prose-sm max-w-3xl space-y-3 leading-relaxed [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1">
      <h1 className="text-2xl font-semibold tracking-tight">{page.title}</h1>
      <Body />
    </article>
  );
}
