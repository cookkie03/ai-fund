import * as React from "react"
import { type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { ToggleGroup as ToggleGroupPrimitive } from "@base-ui/react/toggle-group"
import { Toggle as ToggleItemPrimitive } from "@base-ui/react/toggle"

import { toggleVariants } from "@/components/ui/toggle"

const ToggleGroupContext = React.createContext<
  VariantProps<typeof toggleVariants> & {
    spacing?: number
  }
>({
  size: "default",
  variant: "default",
  spacing: 0,
})

interface ToggleGroupProps
  extends Omit<ToggleGroupPrimitive.Props, "value" | "defaultValue" | "onValueChange">,
    VariantProps<typeof toggleVariants> {
  spacing?: number
  type?: "single" | "multiple"
  value?: any
  defaultValue?: any
  onValueChange?: (value: any) => void
}

function ToggleGroup({
  className,
  variant,
  size,
  spacing = 0,
  type,
  multiple,
  value,
  defaultValue,
  onValueChange,
  children,
  ...props
}: ToggleGroupProps) {
  const isMultiple = multiple ?? (type === "multiple")

  // Normalize single/multiple value for Base UI (which expects array)
  const normalizedValue = React.useMemo(() => {
    if (value === undefined) return undefined
    if (Array.isArray(value)) return value
    return value ? [value] : []
  }, [value])

  const normalizedDefaultValue = React.useMemo(() => {
    if (defaultValue === undefined) return undefined
    if (Array.isArray(defaultValue)) return defaultValue
    return defaultValue ? [defaultValue] : []
  }, [defaultValue])

  const handleValueChange = React.useCallback(
    (vals: string[], _details: ToggleGroupPrimitive.ChangeEventDetails) => {
      if (!onValueChange) return
      if (isMultiple) {
        onValueChange(vals)
      } else {
        onValueChange(vals[0] ?? "")
      }
    },
    [isMultiple, onValueChange]
  )

  return (
    <ToggleGroupPrimitive
      data-slot="toggle-group"
      data-variant={variant}
      data-size={size}
      data-spacing={spacing}
      multiple={isMultiple}
      value={normalizedValue}
      defaultValue={normalizedDefaultValue}
      onValueChange={onValueChange ? handleValueChange : undefined}
      style={{ "--gap": spacing } as React.CSSProperties}
      className={cn(
        "group/toggle-group flex w-fit items-center gap-[--spacing(var(--gap))] rounded-control data-[spacing=default]:data-[variant=outline]:shadow-xs",
        className
      )}
      {...props}
    >
      <ToggleGroupContext.Provider value={{ variant, size, spacing }}>
        {children}
      </ToggleGroupContext.Provider>
    </ToggleGroupPrimitive>
  )
}

interface ToggleGroupItemProps
  extends Omit<ToggleItemPrimitive.Props, "render">,
    VariantProps<typeof toggleVariants> {
  asChild?: boolean
  render?: ToggleItemPrimitive.Props["render"]
}

function ToggleGroupItem({
  className,
  children,
  variant,
  size,
  asChild,
  render,
  ...props
}: ToggleGroupItemProps) {
  const context = React.useContext(ToggleGroupContext)
  const resolvedRender =
    render ?? (asChild && React.isValidElement(children) ? children : undefined)
  const resolvedChildren =
    asChild && React.isValidElement(children) ? undefined : children

  return (
    <ToggleItemPrimitive
      data-slot="toggle-group-item"
      data-variant={context.variant || variant}
      data-size={context.size || size}
      data-spacing={context.spacing}
      render={resolvedRender}
      className={cn(
        toggleVariants({
          variant: context.variant || variant,
          size: context.size || size,
        }),
        "w-auto min-w-0 shrink-0 px-3 focus:z-10 focus-visible:z-10",
        "data-[spacing=0]:rounded-none data-[spacing=0]:shadow-none data-[spacing=0]:first:rounded-l-md data-[spacing=0]:last:rounded-r-md data-[spacing=0]:data-[variant=outline]:border-l-0 data-[spacing=0]:data-[variant=outline]:first:border-l",
        className
      )}
      {...props}
    >
      {resolvedChildren}
    </ToggleItemPrimitive>
  )
}

export { ToggleGroup, ToggleGroupItem }
