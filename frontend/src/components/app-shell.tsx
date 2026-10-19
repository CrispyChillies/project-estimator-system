"use client";

import { BarChart3, FlaskConical, FolderKanban, Gauge, Moon, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useState } from "react";

import { useCurrentUser } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { useUsers } from "@/hooks/queries";

const SIDEBAR_DEFAULT = 260;
const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 400;
const WIDTH_KEY = "calibr.sidebarWidth";

const NAV = [
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/insights", label: "Insights", icon: BarChart3 },
  { href: "/backtest", label: "Backtest", icon: FlaskConical },
  { href: "/settings", label: "Settings", icon: Settings },
];

function UserSwitcher() {
  const { data: users } = useUsers();
  const { userId, setUser } = useCurrentUser();
  const pms = useMemo(() => users?.filter((u) => u.email !== "history@calibr.local") ?? [], [users]);
  useEffect(() => {
    // also replaces a stale id (e.g. after a database reset) with the first demo PM
    if (pms.length && (!userId || !pms.some((u) => u.id === userId))) setUser(pms[0].id);
  }, [userId, pms, setUser]);
  return (
    <Select
      value={userId}
      onValueChange={(v) => v && setUser(v)}
      items={pms.map((u) => ({ value: u.id, label: `${u.name} (${u.role})` }))}
    >
      <SelectTrigger size="sm" className="w-52" aria-label="Demo user">
        <SelectValue placeholder="Select user" />
      </SelectTrigger>
      <SelectContent>
        {pms.map((u) => (
          <SelectItem key={u.id} value={u.id}>
            {u.name} ({u.role})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle theme"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      <Sun className="hidden dark:block" />
      <Moon className="dark:hidden" />
    </Button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [width, setWidth] = useState(SIDEBAR_DEFAULT);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const saved = Number(window.localStorage.getItem(WIDTH_KEY)); // UI preference only
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read preference after hydration
    if (saved) setWidth(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, saved)));
  }, []);
  const startDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = width;
    let latest = startW;
    setDragging(true);
    const move = (ev: PointerEvent) => {
      latest = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startW + ev.clientX - startX));
      setWidth(latest);
    };
    const up = () => {
      setDragging(false);
      window.localStorage.setItem(WIDTH_KEY, String(latest));
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const onHandleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const next = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, width + (e.key === "ArrowRight" ? 16 : -16)));
    setWidth(next);
    window.localStorage.setItem(WIDTH_KEY, String(next));
  };
  return (
    <SidebarProvider
      style={{ "--sidebar-width": `${width}px` } as React.CSSProperties}
      className={dragging ? "select-none **:transition-none!" : undefined}
    >
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <div className="flex items-center gap-2 px-2 py-1.5">
            <div className="flex items-center gap-2 group-data-[collapsible=icon]:hidden">
              <Gauge className="size-5 shrink-0 text-primary" />
              <span className="font-semibold tracking-tight">Calibr</span>
            </div>
            <SidebarTrigger className="ml-auto group-data-[collapsible=icon]:mx-auto" />
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Estimation</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV.map((n) => (
                  <SidebarMenuItem key={n.href}>
                    <SidebarMenuButton
                      isActive={pathname.startsWith(n.href)}
                      tooltip={n.label}
                      render={<Link href={n.href} />}
                    >
                      <n.icon />
                      <span>{n.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <p className="px-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
            Self-learning estimator
          </p>
        </SidebarFooter>
        <SidebarRail />
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar"
          aria-valuemin={SIDEBAR_MIN}
          aria-valuemax={SIDEBAR_MAX}
          aria-valuenow={width}
          tabIndex={0}
          onPointerDown={startDrag}
          onKeyDown={onHandleKey}
          className="absolute inset-y-0 -right-1 z-30 hidden w-2 cursor-col-resize touch-none transition-colors hover:bg-primary/30 focus-visible:bg-primary/40 focus-visible:outline-none md:block group-data-[collapsible=icon]:hidden"
        />
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur">
          <div className="ml-auto flex items-center gap-2">
            <UserSwitcher />
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
