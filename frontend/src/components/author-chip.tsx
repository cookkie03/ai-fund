import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { author as resolveAuthor, type Author } from "@/lib/authors";
import { cn } from "@/lib/utils";

type Props = {
  actor?: string | null;
  author?: Author;
  /** Show the short name beside the monogram. */
  label?: boolean;
  size?: "xs" | "sm";
  className?: string;
  tooltip?: string;
};

/** Monogram in the author's colour: the signature of every mark in the cockpit. */
export function AuthorChip({ actor, author, label = false, size = "sm", className, tooltip }: Props) {
  const a = author ?? resolveAuthor(actor);
  const chip = (
    <span
      className={cn("inline-flex min-w-0 items-center gap-1.5 align-middle", className)}
      aria-label={label ? undefined : `${a.name}${a.channel && a.kind === "human" ? ` (${a.channel})` : ""}`}
    >
      <span
        className={cn(
          "inline-grid shrink-0 place-items-center rounded-[4px] font-semibold tracking-[0.02em]",
          size === "xs" ? "h-4 min-w-4 px-[3px] text-[9px] leading-none" : "h-[18px] min-w-[18px] px-1 text-[10px] leading-none",
        )}
        style={{
          color: a.color,
          backgroundColor: `color-mix(in oklch, ${a.color} 17%, transparent)`,
          boxShadow: `inset 0 0 0 1px color-mix(in oklch, ${a.color} 30%, transparent)`,
        }}
      >
        {a.initials}
      </span>
      {label && <span className="truncate text-fg-muted">{a.short}</span>}
    </span>
  );
  if (label && !tooltip) return chip;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{chip}</TooltipTrigger>
      <TooltipContent side="top">{tooltip ?? `${a.name}${a.kind === "human" && a.channel ? ` · via ${a.channel}` : ""}`}</TooltipContent>
    </Tooltip>
  );
}
