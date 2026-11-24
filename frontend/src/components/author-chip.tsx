import { Avatar, AvatarFallback } from "@/components/ui/avatar";
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
      <Avatar
        data-part="monogram"
        className={cn(
          "shrink-0 rounded-full font-bold tracking-[-0.01em]",
          size === "xs"
            ? "size-[18px] text-[8.5px]"
            : size === "md"
              ? "size-7 text-[11px]"
              : size === "lg"
                ? "size-9 text-[13px]"
                : "size-5 text-[9.5px]",
        )}
        style={{
          ["--author" as string]: a.color,
          backgroundColor: a.color,
          color: "var(--desk)",
        }}
      >
        <AvatarFallback style={{ backgroundColor: a.color, color: "var(--desk)" }}>
          {a.ticker && size === "lg" ? <span className={a.ticker.length > 3 ? "text-[10px] tracking-[-0.03em]" : "text-[11px]"}>{a.ticker.slice(0, 4)}</span> : a.initials}
        </AvatarFallback>
      </Avatar>
      {label && <span className="truncate text-fg-muted">{a.short}</span>}
    </span>
  );
  if (label && !tooltip) return chip;
  return (
    <Tooltip>
      <TooltipTrigger render={chip} />
      <TooltipContent side="top">{tooltip ?? `${a.name}${a.kind === "human" && a.channel ? ` · via ${a.channel}` : ""}`}</TooltipContent>
    </Tooltip>
  );
}
