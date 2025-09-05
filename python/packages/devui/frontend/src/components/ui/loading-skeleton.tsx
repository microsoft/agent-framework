import { cn } from "@/lib/utils"

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {}

function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-muted", 
        className
      )}
      {...props}
    />
  )
}

interface LoadingSkeletonProps {
  variant?: "card" | "list" | "text" | "button" | "agent-switcher"
  count?: number
  className?: string
}

function LoadingSkeleton({ variant = "text", count = 1, className }: LoadingSkeletonProps) {
  const skeletons = Array.from({ length: count }, (_, i) => (
    <div key={i}>
      {getSkeletonContent(variant)}
    </div>
  ))

  return <div className={className}>{skeletons}</div>
}

function getSkeletonContent(variant: LoadingSkeletonProps["variant"]) {
  switch (variant) {
    case "card":
      return (
        <div className="space-y-3 p-4">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3 w-full" />
        </div>
      )
    case "list":
      return (
        <div className="flex items-center space-x-3 p-2">
          <Skeleton className="h-6 w-6 rounded-full" />
          <div className="space-y-1 flex-1">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      )
    case "button":
      return <Skeleton className="h-9 w-24" />
    case "agent-switcher":
      return (
        <div className="flex items-center justify-between w-64 p-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-4" />
            <Skeleton className="h-4 w-32" />
          </div>
          <Skeleton className="h-4 w-4" />
        </div>
      )
    default:
      return <Skeleton className="h-4 w-full" />
  }
}

export { Skeleton, LoadingSkeleton }