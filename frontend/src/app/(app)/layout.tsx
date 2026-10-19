"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/app-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/hooks/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { data: me, isLoading } = useMe();
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (!isLoading && me === null) router.replace(`/signin?next=${encodeURIComponent(pathname)}`);
  }, [isLoading, me, router, pathname]);
  if (!me)
    return (
      <div className="p-6">
        <Skeleton className="h-10 w-64" />
      </div>
    );
  return <AppShell>{children}</AppShell>;
}
