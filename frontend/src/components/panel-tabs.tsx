import { Tabs as TabsPrimitive } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Dense underline tabs for docks and side panels (the TWS / TradingView pattern). */
export const PanelTabs = TabsPrimitive.Root;

export function PanelTabsList({ className, children, end }: { className?: string; children: ReactNode; end?: ReactNode }) {
  return (
    <div className={cn("flex h-9 shrink-0 items-stretch border-b border-line pl-1 pr-2", className)}>
      <TabsPrimitive.List className="flex min-w-0 items-stretch gap-0.5 overflow-x-auto">{children}</TabsPrimitive.List>
      {end && <div className="ml-auto flex shrink-0 items-center gap-1 pl-2">{end}</div>}
    </div>
  );
}

export function PanelTab({ className, children, count, tone, ...props }: ComponentProps<typeof TabsPrimitive.Trigger> & { count?: number; tone?: "warn" }) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "group relative inline-flex items-center gap-1.5 whitespace-nowrap px-2.5 text-xs font-medium text-fg-subtle transition-colors duration-150 outline-none",
        "hover:text-fg data-[state=active]:text-fg focus-visible:bg-hover",
        "after:absolute after:inset-x-2 after:bottom-[-1px] after:h-[2px] after:rounded-full after:bg-accent-c after:opacity-0 after:transition-opacity data-[state=active]:after:opacity-100",
        className,
      )}
      {...props}
    >
      {children}
      {count !== undefined && count > 0 && (
        <span
          className={cn(
            "num rounded px-1 text-[10px] leading-4",
            tone === "warn" ? "bg-warn-soft text-warn" : "bg-hover text-fg-muted group-data-[state=active]:text-fg",
          )}
        >
          {count}
        </span>
      )}
    </TabsPrimitive.Trigger>
  );
}

export function PanelTabContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("min-h-0 flex-1 outline-none data-[state=inactive]:hidden", className)} {...props} />;
}
