import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import type { UIMessage } from "ai";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps, HTMLAttributes } from "react";

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage["role"];
};

export const Message = ({ className, from, ...props }: MessageProps) => (
  <div
    className={cn(
      "group flex w-full py-2.5",
      from === "user" ? "is-user justify-end" : "is-assistant justify-start",
      className
    )}
  >
    <div
      className={cn(
        "flex items-end gap-3.5 min-w-[240px] sm:min-w-[280px] max-w-[90%] sm:max-w-[85%]",
        from === "user" && "flex-row-reverse"
      )}
      {...props}
    />
  </div>
);

const messageContentVariants = cva(
  "is-user:dark flex flex-col gap-2.5 overflow-hidden rounded-2xl text-base shadow-sm min-w-0 flex-1",
  {
    variants: {
      variant: {
        contained: [
          "px-5 py-3.5",
          "group-[.is-user]:bg-primary group-[.is-user]:text-primary-foreground group-[.is-user]:rounded-2xl group-[.is-user]:shadow-md",
          "group-[.is-assistant]:bg-secondary group-[.is-assistant]:text-foreground group-[.is-assistant]:rounded-2xl group-[.is-assistant]:border group-[.is-assistant]:border-border/50",
        ],
        flat: [
          "group-[.is-user]:bg-secondary group-[.is-user]:px-5 group-[.is-user]:py-3.5 group-[.is-user]:text-foreground group-[.is-user]:rounded-2xl",
          "group-[.is-assistant]:text-foreground",
        ],
      },
    },
    defaultVariants: {
      variant: "contained",
    },
  }
);

export type MessageContentProps = HTMLAttributes<HTMLDivElement> &
  VariantProps<typeof messageContentVariants>;

export const MessageContent = ({
  children,
  className,
  variant,
  ...props
}: MessageContentProps) => (
  <div
    className={cn(messageContentVariants({ variant, className }))}
    {...props}
  >
    {children}
  </div>
);

export type MessageAvatarProps = ComponentProps<typeof Avatar> & {
  src: string;
  name?: string;
};

export const MessageAvatar = ({
  src,
  name,
  className,
  ...props
}: MessageAvatarProps) => (
  <Avatar className={cn("size-8 ring-1 ring-border", className)} {...props}>
    <AvatarImage alt="" className="mt-0 mb-0" src={src} />
    <AvatarFallback>{name?.slice(0, 2) || "ME"}</AvatarFallback>
  </Avatar>
);
