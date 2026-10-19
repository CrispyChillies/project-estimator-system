"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { createContext, useContext, useEffect, useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getUserId, setUserId } from "@/lib/api";
import { EstimateJobsProvider } from "@/hooks/estimate-jobs";

interface UserCtx {
  userId: string | null;
  setUser: (id: string) => void;
}

const UserContext = createContext<UserCtx>({ userId: null, setUser: () => {} });

export function useCurrentUser() {
  return useContext(UserContext);
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: false } } }),
  );
  const [userId, setUid] = useState<string | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read UI preference after hydration
    setUid(getUserId());
  }, []);
  const setUser = (id: string) => {
    setUserId(id);
    setUid(id);
    void client.invalidateQueries();
  };
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <UserContext.Provider value={{ userId, setUser }}>
          <TooltipProvider>
            <EstimateJobsProvider>{children}</EstimateJobsProvider>
          </TooltipProvider>
          <Toaster richColors position="bottom-right" />
        </UserContext.Provider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
