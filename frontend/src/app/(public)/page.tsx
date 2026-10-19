import Link from "next/link";

import { Wordmark } from "@/components/brand";
import { Button } from "@/components/ui/button";

export default function Landing() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6 text-center">
      <Wordmark descriptor />
      <h1 className="max-w-2xl text-3xl font-semibold tracking-tight">Turn client briefs into reviewable, calibrated estimates.</h1>
      <div className="flex gap-2">
        <Button render={<Link href="/signin" />}>Sign in</Button>
        <Button variant="outline" render={<Link href="/signup" />}>Create account</Button>
      </div>
    </main>
  );
}
