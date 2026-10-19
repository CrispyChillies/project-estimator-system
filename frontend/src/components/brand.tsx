import { cn } from "@/lib/utils";

/** Original Calibr mark: a calibration gauge — three tick marks on an arc and a needle settling on the target. */
export function LogoMark({ className, title = "Calibr" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 32 32" role="img" aria-label={title} className={cn("size-6", className)}>
      <rect x="1" y="1" width="30" height="30" rx="8" className="fill-primary" />
      <path d="M7.5 20.5a8.5 8.5 0 0 1 17 0" fill="none" strokeWidth="2.4" strokeLinecap="round"
        className="stroke-primary-foreground/45" />
      <path d="M9.6 14.4l1.5 1.2M16 11.4v1.9M22.4 14.4l-1.5 1.2" strokeWidth="2" strokeLinecap="round"
        className="stroke-primary-foreground" />
      <path d="M16 20.5l3.4-4.6" strokeWidth="2.6" strokeLinecap="round" className="stroke-primary-foreground" />
      <circle cx="16" cy="20.5" r="2.2" className="fill-primary-foreground" />
    </svg>
  );
}

export function Wordmark({ className, descriptor = false }: { className?: string; descriptor?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="flex flex-col leading-none">
        <span className="font-semibold tracking-tight">Calibr</span>
        {descriptor && <span className="text-[10px] text-muted-foreground">Project Calibrate UI</span>}
      </span>
    </span>
  );
}
