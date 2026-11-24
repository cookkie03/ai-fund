import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** Header row of a tile: title, quiet metadata, actions. No divider: the tile's padding separates it. */
export function TileHeader({ title, meta, hint, children, className }: { title: ReactNode; meta?: ReactNode; hint?: string; children?: ReactNode; className?: string }) {
  return (
    <header className={cn("flex h-11 shrink-0 items-center gap-2 pl-4 pr-2", className)}>
      <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg" title={hint}>{title}</h2>
      {meta && <span className="num min-w-0 truncate rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-subtle">{meta}</span>}
      {children && <div className="ml-auto flex shrink-0 items-center gap-0.5">{children}</div>}
    </header>
  );
}

/** Square icon button used in tile headers and toolbars (28 px, item radius). */
export function IconButton({
  icon: Icon,
  label,
  shortcut,
  onClick,
  active,
  disabled,
  className,
}: {
  icon: LucideIcon;
  label: string;
  shortcut?: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={label}
            aria-pressed={active}
            onClick={onClick}
            disabled={disabled}
            className={cn(
              "size-7 rounded-item p-0",
              active ? "text-fg bg-hover" : "text-fg-subtle hover:text-fg",
              className,
            )}
          >
            <Icon className="size-[15px]" strokeWidth={1.75} />
          </Button>
        }
      />
      <TooltipContent>
        {label}
        {shortcut && <kbd className="ml-2 rounded-tag bg-hover px-1 py-px font-sans text-2xs text-fg-subtle">{shortcut}</kbd>}
      </TooltipContent>
    </Tooltip>
  );
}
