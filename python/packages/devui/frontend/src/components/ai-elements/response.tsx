"use client";

import { cn } from "@/lib/utils";
import { memo } from "react";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";

type ResponseProps = {
  children: string;
  className?: string;
};

export const Response = memo(
  ({ className, children, ...props }: ResponseProps) => (
    <MarkdownRenderer
      content={children}
      className={cn(
        "size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
        className
      )}
      {...props}
    />
  ),
  (prevProps, nextProps) => prevProps.children === nextProps.children
);

Response.displayName = "Response";
