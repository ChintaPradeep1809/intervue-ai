import { brand } from "@intervue/config";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7", className)}>
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <g className="fill-primary-foreground">
        <rect x="7" y="13" width="2.6" height="6" rx="1.3" />
        <rect x="11.5" y="9.5" width="2.6" height="13" rx="1.3" />
        <rect x="16" y="11.5" width="2.6" height="9" rx="1.3" />
        <rect x="20.5" y="7.5" width="2.6" height="17" rx="1.3" opacity="0.85" />
        <circle cx="25.6" cy="16" r="1.4" opacity="0.7" />
      </g>
    </svg>
  );
}

export function Logo({ href = "/", className, inverted }: { href?: string; className?: string; inverted?: boolean }) {
  return (
    <Link href={href} className={cn("inline-flex items-center gap-2 rounded-md font-semibold tracking-tight focus-visible:outline-2", className)}>
      <LogoMark />
      <span className={cn("text-[15px]", inverted && "text-studio-foreground")}>{brand.name}</span>
    </Link>
  );
}
