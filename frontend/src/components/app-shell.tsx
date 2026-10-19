"use client";

import {
  BarChart3,
  Compass,
  FlaskConical,
  FolderKanban,
  LayoutDashboard,
  LifeBuoy,
  ListChecks,
  LogOut,
  Moon,
  Settings,
  ShieldCheck,
  Sun,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { CurrencyToggle } from "@/components/currency-toggle";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { LogoMark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { useMe, useOnboarding, useSignOut } from "@/hooks/auth";

const SIDEBAR_DEFAULT = 260;
const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 400;
const WIDTH_KEY = "calibr.sidebarWidth";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/insights", label: "Insights", icon: BarChart3 },
  { href: "/backtest", label: "Backtest", icon: FlaskConical },
  { href: "/settings", label: "Settings", icon: Settings },
];

function UserMenu() {
  const { data: me } = useMe();
  const signOut = useSignOut();
  const { update } = useOnboarding();
  const router = useRouter();
  if (!me) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="sm" className="gap-2" title="Account menu" data-tour="account-menu" />}>
        <span aria-hidden className="flex size-6 items-center justify-center rounded-full bg-primary/15 text-xs font-medium text-primary">
          {me.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="sr-only max-w-32 truncate sm:not-sr-only">{me.name}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <div className="px-2 py-1.5 text-xs text-muted-foreground">{me.role === "admin" ? "Administrator" : "Member"}</div>
        <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs text-muted-foreground">
          <span>Currency</span>
          <CurrencyToggle />
        </div>
        <DropdownMenuItem render={<Link href="/profile" />}>
          <UserRound /> Profile
        </DropdownMenuItem>
        <DropdownMenuItem render={<Link href="/help" />}>
          <LifeBuoy /> Help & guides
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => update({ checklist_dismissed: false })} render={<Link href="/dashboard" />}>
          <ListChecks /> Getting started checklist
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            update({ tour_done: false, tour_step: 0, welcome_seen: true });
            router.push("/dashboard");
          }}
        >
          <Compass /> Take the tour again
        </DropdownMenuItem>
        {me.role === "admin" && (
          <DropdownMenuItem render={<Link href="/admin" />}>
            <ShieldCheck /> Admin
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => signOut.mutate()}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
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
              <Link href="/dashboard" className="flex items-center gap-2">
                <LogoMark className="size-6 shrink-0" />
                <span className="font-semibold tracking-tight">Calibr</span>
              </Link>
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
                      data-tour={`nav-${n.href.slice(1)}`}
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
          <p className="px-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">Project Calibrate UI</p>
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
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
