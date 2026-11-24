import * as React from "react"
import { cn } from "@/lib/utils"
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip"

interface TooltipProviderProps extends TooltipPrimitive.Provider.Props {
  delayDuration?: number
}

function TooltipProvider({
  delayDuration = 350,
  delay,
  ...props
}: TooltipProviderProps) {
  return (
    <TooltipPrimitive.Provider
      data-slot="tooltip-provider"
      delay={delay ?? delayDuration}
      {...props}
    />
  )
}

function Tooltip({
  ...props
}: TooltipPrimitive.Root.Props) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />
}

interface TooltipTriggerProps
  extends Omit<TooltipPrimitive.Trigger.Props, "render"> {
  asChild?: boolean
  render?: TooltipPrimitive.Trigger.Props["render"]
}

function TooltipTrigger({
  asChild,
  render,
  children,
  ...props
}: TooltipTriggerProps) {
  const resolvedRender =
    render ?? (asChild && React.isValidElement(children) ? children : undefined)
  const resolvedChildren =
    asChild && React.isValidElement(children) ? undefined : children

  return (
    <TooltipPrimitive.Trigger
      data-slot="tooltip-trigger"
      render={resolvedRender}
      {...props}
    >
      {resolvedChildren}
    </TooltipPrimitive.Trigger>
  )
}

interface TooltipContentProps extends TooltipPrimitive.Popup.Props {
  sideOffset?: TooltipPrimitive.Positioner.Props["sideOffset"]
  side?: TooltipPrimitive.Positioner.Props["side"]
  align?: TooltipPrimitive.Positioner.Props["align"]
  alignOffset?: TooltipPrimitive.Positioner.Props["alignOffset"]
}

function TooltipContent({
  className,
  side = "top",
  sideOffset = 6,
  align = "center",
  alignOffset = 0,
  children,
  ...props
}: TooltipContentProps) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        className="isolate z-50"
      >
        <TooltipPrimitive.Popup
          data-slot="tooltip-content"
          className={cn(
            "z-50 w-fit origin-(--transform-origin) animate-in rounded-item border border-line-strong/70 bg-raised px-2 py-1 text-xs text-balance text-fg shadow-[0_6px_20px_-6px_rgb(0_0_0/0.6)] fade-in-0 zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
            className
          )}
          {...props}
        >
          {children}
        </TooltipPrimitive.Popup>
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  )
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
