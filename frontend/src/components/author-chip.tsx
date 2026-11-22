import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { author as resolveAuthor, type Author } from "@/lib/authors";
import { cn } from "@/lib/utils";

type Props = {
  actor?: string | null;
  author?: Author;
  /** Show the short name beside the monogram. */
  label?: boolean;
  /** xs 18 px (dense rows), sm 20 px, md 28 px (messages), lg 36 px (agent seats). */
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
  tooltip?: string;
};

/** Filled round avatar in the author's colour: the signature of every mark in the cockpit. */
export function AuthorChip({ actor, author, label = false, size = "sm", className, tooltip }: Props) {
  const a = author ?? resolveAuthor(actor);
  const chip = (
    <span
      className={cn("inline-flex min-w-0 items-center gap-1.5 align-middle", className)}
      aria-label={label ? undefined : `${a.name}${a.channel && a.kind === "human" ? ` (${a.channel})` : ""}`}
    >
      <span
        data-part="monogram"
        className={cn(
          "inline-grid shrink-0 place-items-center rounded-full font-bold tracking-[-0.01em] text-[oklch(0.16_0.01_260)]",
          size === "xs"
            ? "size-[18px] text-[8.5px] leading-none"
            : size === "md"
              ? "size-7 text-[11px] leading-none"
              : size === "lg"
                ? "size-9 text-[13px] leading-none"
                : "size-5 text-[9.5px] leading-none",
        )}
        style={{
          ["--author" as string]: a.color,
          backgroundColor: a.color,
          boxShadow: "inset 0 0.5px 0 oklch(1 0 0 / 0.3)",
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
