"use client";

import { BarChart3, FlaskConical, FolderKanban, Gauge, Moon, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useMemo } from "react";

import { useCurrentUser } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
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
    if (!userId && pms.length) setUser(pms[0].id);
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
  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <div className="flex items-center gap-2 px-2 py-1.5">
            <Gauge className="size-5 shrink-0 text-primary" />
            <span className="font-semibold tracking-tight group-data-[collapsible=icon]:hidden">Calibr</span>
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
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
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
