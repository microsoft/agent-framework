import React from "react";
import { X } from "lucide-react";
import { Button } from "./button";

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

interface DialogContentProps {
  children: React.ReactNode;
  className?: string;
}

interface DialogHeaderProps {
  children: React.ReactNode;
  className?: string;
}

interface DialogTitleProps {
  children: React.ReactNode;
  className?: string;
}

interface DialogDescriptionProps {
  children: React.ReactNode;
  className?: string;
}

interface DialogFooterProps {
  children: React.ReactNode;
}

export function Dialog({ open, onOpenChange, children }: DialogProps) {
  if (!open) return null;

  const handleBackdropClick = () => {
    // Close the modal when backdrop is clicked
    onOpenChange(false);
  };

  const handleContentClick = (e: React.MouseEvent) => {
    // Stop any clicks inside the content from bubbling to backdrop
    e.stopPropagation();
  };

  const handleContentMouseDown = (e: React.MouseEvent) => {
    // Prevent mousedown from bubbling during text selection
    e.stopPropagation();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop - handles clicks to close */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={handleBackdropClick}
      />

      {/* Modal content - positioned above backdrop with z-index */}
      <div
        className="relative z-10"
        onClick={handleContentClick}
        onMouseDown={handleContentMouseDown}
        onMouseUp={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function DialogContent({
  children,
  className = "",
}: DialogContentProps) {
  // Default width classes if none provided
  const hasWidthClass = className.includes('w-[') || className.includes('w-full') || className.includes('max-w-');
  const defaultWidthClasses = hasWidthClass ? '' : 'max-w-lg w-full';

  return (
    <div
      className={`relative bg-background border rounded-lg shadow-lg max-h-[90vh] overflow-hidden ${defaultWidthClasses} ${className}`}
    >
      {children}
    </div>
  );
}

export function DialogHeader({ children, className = "" }: DialogHeaderProps) {
  return (
    <div className={`space-y-2 ${className}`}>
      {children}
    </div>
  );
}

export function DialogTitle({ children, className = "" }: DialogTitleProps) {
  return <h2 className={`text-lg font-semibold ${className}`}>{children}</h2>;
}

export function DialogDescription({ children, className = "" }: DialogDescriptionProps) {
  return <p className={`text-sm text-muted-foreground ${className}`}>{children}</p>;
}

export function DialogClose({ onClose }: { onClose: () => void }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClose}
      className="absolute top-4 right-4 h-8 w-8 p-0 rounded-sm opacity-70 hover:opacity-100"
    >
      <X className="h-4 w-4" />
    </Button>
  );
}

export function DialogFooter({ children }: DialogFooterProps) {
  return (
    <div className="flex justify-end gap-2 p-4 border-t bg-muted/50">
      {children}
    </div>
  );
}
