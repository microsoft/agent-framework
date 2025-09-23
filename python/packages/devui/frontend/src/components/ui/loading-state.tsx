import { LoadingSpinner } from "./loading-spinner"
import { cn } from "@/lib/utils"

interface LoadingStateProps {
  message?: string
  description?: string
  size?: "sm" | "md" | "lg"
  className?: string
  fullPage?: boolean
}

export function LoadingState({ 
  message = "Loading...", 
  description,
  size = "md",
  className,
  fullPage = false
}: LoadingStateProps) {
  const content = (
    <div className={cn(
      "flex flex-col items-center justify-center gap-3",
      fullPage ? "min-h-[50vh]" : "py-8",
      className
    )}>
      <LoadingSpinner size={size} className="text-muted-foreground" />
      <div className="text-center space-y-1">
        <p className={cn(
          "font-medium text-muted-foreground",
          size === "sm" && "text-sm",
          size === "lg" && "text-lg"
        )}>
          {message}
        </p>
        {description && (
          <p className="text-sm text-muted-foreground/80">
            {description}
          </p>
        )}
      </div>
    </div>
  )

  if (fullPage) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        {content}
      </div>
    )
  }

  return content
}