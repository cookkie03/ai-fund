import { showSwitcher, switchVariant, variant, VARIANTS } from "@/lib/variant";
import { cn } from "@/lib/utils";

/** Exploration aid: flip between candidate directions on the same live data. */
export function VariantSwitcher() {
  if (!showSwitcher) return null;
  return (
    <div
      role="radiogroup"
      aria-label="Variante di design"
      className="fixed bottom-3 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-0.5 rounded-full bg-[oklch(0.12_0.005_260/0.92)] p-1 text-xs shadow-[0_0_0_0.5px_oklch(1_0_0/0.12),0_10px_30px_oklch(0_0_0/0.55)] max-md:bottom-16"
    >
      {VARIANTS.map((v) => (
        <button
          key={v.id}
          role="radio"
          aria-checked={variant === v.id}
          title={v.hint}
          onClick={() => variant !== v.id && switchVariant(v.id)}
          className={cn(
            "h-7 rounded-full px-3 font-medium transition-colors duration-150",
            variant === v.id ? "bg-[oklch(0.96_0_0)] text-[oklch(0.15_0_0)]" : "text-[oklch(0.75_0.01_260)] hover:text-[oklch(0.96_0_0)]",
          )}
        >
          <span className="max-md:hidden">{v.label}</span>
          <span className="md:hidden">{v.id === "current" ? "Attuale" : v.id.toUpperCase()}</span>
        </button>
      ))}
    </div>
  );
}
