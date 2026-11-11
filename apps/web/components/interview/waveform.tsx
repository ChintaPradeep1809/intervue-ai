"use client";

import { cn } from "@/lib/utils";

/** Interviewer presence waveform. `active` animates the bars; `level` (0..1) scales them for mic input. */
export function Waveform({
  active,
  level,
  bars = 24,
  className,
  barClassName,
}: {
  active: boolean;
  level?: number;
  bars?: number;
  className?: string;
  barClassName?: string;
}) {
  return (
    <div className={cn("flex h-12 items-center justify-center gap-[3px]", className)} aria-hidden>
      {Array.from({ length: bars }).map((_, i) => {
        const shape = Math.round((0.35 + 0.65 * Math.sin((i / (bars - 1)) * Math.PI)) * 1000) / 1000;
        const scale = level !== undefined ? Math.round(Math.max(0.12, Math.min(1, level * 1.6 * shape + 0.1)) * 100) / 100 : 0.18;
        return (
          <span
            key={i}
            className={cn("block h-full w-[3px] origin-center rounded-full bg-current transition-transform duration-100", barClassName)}
            style={
              active
                ? { animation: `wave ${(0.9 + ((i * 37) % 7) / 10).toFixed(1)}s ease-in-out ${((i % 6) * 0.08).toFixed(2)}s infinite`, transform: `scaleY(${shape})` }
                : { transform: `scaleY(${scale})` }
            }
          />
        );
      })}
    </div>
  );
}
