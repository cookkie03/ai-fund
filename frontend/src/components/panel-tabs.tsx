import { Tabs as TabsPrimitive } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Segmented tabs for tile headers: control radius outside, item radius inside. */
export const PanelTabs = TabsPrimitive.Root;

export function PanelTabsList({ className, children, end }: { className?: string; children: ReactNode; end?: ReactNode }) {
  return (
    <div data-part="tabs" className={cn("flex h-11 shrink-0 items-center gap-2 pl-2 pr-2", className)}>
      <TabsPrimitive.List className="seg min-w-0 overflow-x-auto">{children}</TabsPrimitive.List>
      {end && <div className="ml-auto flex shrink-0 items-center gap-1 pl-2">{end}</div>}
    </div>
  );
}

export function PanelTab({ className, children, count, tone, onClick, ...props }: ComponentProps<typeof TabsPrimitive.Trigger> & { count?: number; tone?: "warn" }) {
  return (
    <TabsPrimitive.Trigger
      data-part="tab"
      className={cn(
        "seg-item group outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
        className,
      )}
      // Radix selects on mousedown; a bare click (assistive tech, scripted clicks) only lands here. Focus selects
      // the tab under automatic activation, so the click works too.
      onClick={(e) => {
        onClick?.(e);
        if (!e.defaultPrevented && document.activeElement !== e.currentTarget) e.currentTarget.focus();
      }}
      {...props}
    >
      {children}
      {count !== undefined && count > 0 && (
        <span
          className={cn(
            "num rounded-tag px-1 text-[10px] leading-4",
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
