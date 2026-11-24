import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";
import type { ReactNode } from "react";
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

export function PanelTab({ className, children, count, tone, onClick, ...props }: TabsPrimitive.Tab.Props & { count?: number; tone?: "warn" }) {
  return (
    <TabsPrimitive.Tab
      data-part="tab"
      className={cn(
        "seg-item group outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
        className,
      )}
      onClick={(e) => {
        onClick?.(e);
        if (!e.defaultPrevented && document.activeElement !== e.currentTarget) (e.currentTarget as HTMLElement).focus();
      }}
      {...props}
    >
      {children}
      {count !== undefined && count > 0 && (
        <span
          className={cn(
            "num rounded-tag px-1 text-[10px] leading-4",
            tone === "warn" ? "bg-warn-soft text-warn" : "bg-hover text-fg-muted group-data-active:text-fg group-data-[state=active]:text-fg",
          )}
        >
          {count}
        </span>
      )}
    </TabsPrimitive.Tab>
  );
}

export function PanelTabContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return <TabsPrimitive.Panel className={cn("min-h-0 flex-1 outline-none data-hidden:hidden data-[state=inactive]:hidden", className)} {...props} />;
}
