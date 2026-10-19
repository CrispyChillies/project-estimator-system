"use client";

import Link from "next/link";

import { Wordmark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { useMe } from "@/hooks/auth";

export function PublicHeader({ links = true }: { links?: boolean }) {
  const { data: me } = useMe();
  return (
    <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
      <nav className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4" aria-label="Main">
        <Link href="/" aria-label="Calibr — Project Calibrate UI, home">
          <Wordmark descriptor />
        </Link>
        {links && (
          <div className="ml-4 hidden gap-4 text-sm text-muted-foreground md:flex">
            <Link href="/#features" className="hover:text-foreground">Features</Link>
            <Link href="/#how-it-works" className="hover:text-foreground">How it works</Link>
            <Link href="/help" className="hover:text-foreground">Help</Link>
          </div>
        )}
        <div className="ml-auto flex items-center gap-2">
          {me ? (
            <Button size="sm" render={<Link href="/dashboard" />}>Open app</Button>
          ) : (
            <>
              <Button size="sm" variant="ghost" render={<Link href="/signin" />}>Sign in</Button>
              <Button size="sm" render={<Link href="/signup" />}>Get started</Button>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
