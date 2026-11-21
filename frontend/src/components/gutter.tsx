import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import { cn } from "@/lib/utils";

/**
 * The gap between two tiles doubles as their resize handle, like VS Code's sashes.
 * `direction` is the sign that turns pointer travel into size: 1 when the panel grows with the pointer.
 */
export function Gutter({
  orientation,
  label,
  value,
  min,
  max,
  direction,
  onResize,
  onReset,
  className,
}: {
  orientation: "vertical" | "horizontal";
  label: string;
  value: number;
  min: number;
  max: number;
  direction: 1 | -1;
  onResize: (px: number) => void;
  onReset: () => void;
  className?: string;
}) {
  const drag = useRef<{ start: number; from: number } | null>(null);
  const vertical = orientation === "vertical";

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { start: vertical ? e.clientX : e.clientY, from: value };
    document.documentElement.dataset.resizing = orientation;
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const delta = (vertical ? e.clientX : e.clientY) - drag.current.start;
    onResize(drag.current.from + direction * delta);
  };
  const end = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    drag.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    delete document.documentElement.dataset.resizing;
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 48 : 16;
    const grow = vertical ? (direction === 1 ? "ArrowRight" : "ArrowLeft") : direction === 1 ? "ArrowDown" : "ArrowUp";
    const shrink = vertical ? (direction === 1 ? "ArrowLeft" : "ArrowRight") : direction === 1 ? "ArrowUp" : "ArrowDown";
    if (e.key === grow) onResize(value + step);
    else if (e.key === shrink) onResize(value - step);
    else if (e.key === "Home") onResize(min);
    else if (e.key === "End") onResize(max);
    else return;
    e.preventDefault();
  };

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-orientation={orientation}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      title={`${label} · doppio clic per ripristinare`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onLostPointerCapture={end}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      className={cn(
        "group relative shrink-0 touch-none outline-none",
        vertical ? "w-2.5 cursor-col-resize" : "h-2.5 cursor-row-resize",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "absolute rounded-full bg-accent-c opacity-0 transition-opacity duration-150 group-hover:opacity-60 group-focus-visible:opacity-100 group-active:opacity-100",
          vertical ? "inset-y-3 left-1/2 w-0.5 -translate-x-1/2" : "inset-x-3 top-1/2 h-0.5 -translate-y-1/2",
        )}
      />
    </div>
  );
}
