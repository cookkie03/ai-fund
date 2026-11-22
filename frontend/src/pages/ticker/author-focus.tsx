import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { author as resolve } from "@/lib/authors";
import { cn } from "@/lib/utils";

/**
 * Author layers for the dossier, as on the chart: hovering an author (or pinning one from the legend)
 * lights every fact they signed across the mosaic and lets the rest recede.
 */
type Ctx = { hover: string | null; pinned: string | null; setHover: (a: string | null) => void; togglePin: (a: string) => void };

const AuthorFocusCtx = createContext<Ctx>({ hover: null, pinned: null, setHover: () => {}, togglePin: () => {} });

/** Same identity whatever channel or case the Runtime used (cockpit/telegram are all Luca). */
export const authorKey = (actor: string | null | undefined) => resolve(actor).id;

export function AuthorFocusProvider({ children }: { children: ReactNode }) {
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const value = useMemo<Ctx>(() => ({ hover, pinned, setHover, togglePin: (a) => setPinned((p) => (p === a ? null : a)) }), [hover, pinned]);
  return <AuthorFocusCtx.Provider value={value}>{children}</AuthorFocusCtx.Provider>;
}

export function useAuthorFocus() {
  const c = useContext(AuthorFocusCtx);
  return { ...c, focus: c.hover ?? c.pinned };
}

/** A fact signed by `author`: recedes while another author is in focus. */
export function Signed({ by, className, children, as: Tag = "div" }: { by: string | null; className?: string; children: ReactNode; as?: "div" | "li" | "article" }) {
  const { focus } = useAuthorFocus();
  const key = by ? authorKey(by) : null;
  const lit = !!focus && key === focus;
  return (
    <Tag data-author={key ?? undefined} className={cn("transition-opacity duration-200", focus && !lit && "opacity-30", className)}>
      {children}
    </Tag>
  );
}

/** The signature avatar: hovering it puts its author in focus. */
export function SignatureChip({ by, size = "sm", label = false, className, tooltip }: { by: string; size?: "xs" | "sm" | "md"; label?: boolean; className?: string; tooltip?: string }) {
  const { setHover } = useAuthorFocus();
  const key = authorKey(by);
  return (
    <span onMouseEnter={() => setHover(key)} onMouseLeave={() => setHover(null)} className={cn("inline-flex", className)}>
      <AuthorChip actor={by} size={size} label={label} tooltip={tooltip} />
    </span>
  );
}
