import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * A hidden tile leaves its edge behind: a slim tile with the tile's icon and name that reopens it on click,
 * so a panel closed with the shortcut never needs the shortcut to come back. Like a tile seen from the side.
 */
export function CollapsedRail({
  side,
  label,
  icon: Icon,
  shortcut,
  onOpen,
  badge,
  className,
}: {
  side: "left" | "right" | "bottom";
  label: string;
  icon: LucideIcon;
  shortcut?: string;
  onOpen: () => void;
  /** A count that must stay visible while hidden (orders waiting for approval). */
  badge?: ReactNode;
  className?: string;
}) {
  const vertical = side !== "bottom";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onOpen}
          aria-label={`Mostra ${label.toLowerCase()}`}
          data-rail={side}
          className={cn(
            "group flex shrink-0 items-center gap-2 rounded-tile bg-ground text-fg-subtle transition-[background-color,color] duration-150 hover:bg-hover hover:text-fg focus-visible:text-fg",
            side === "left" ? "tile-enter-left" : side === "right" ? "tile-enter-right" : "tile-enter-bottom",
            vertical ? "w-8 flex-col py-2.5" : "h-8 w-full px-3",
            className,
          )}
        >
          <span className="grid size-6 shrink-0 place-items-center rounded-item">
            <Icon className="size-[15px]" strokeWidth={1.75} aria-hidden />
          </span>
          {badge}
          <span className={cn("whitespace-nowrap text-2xs font-medium", vertical && "[writing-mode:vertical-rl]", side === "left" && "rotate-180")}>{label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side={side === "left" ? "right" : side === "right" ? "left" : "top"}>
        Mostra {label.toLowerCase()}
        {shortcut && <kbd className="ml-2 rounded-tag bg-hover px-1 py-px font-sans text-2xs text-fg-subtle">{shortcut}</kbd>}
      </TooltipContent>
    </Tooltip>
  );
}
