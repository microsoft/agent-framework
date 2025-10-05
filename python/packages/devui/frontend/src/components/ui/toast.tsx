/**
 * Simple toast notification component
 * Displays floating notifications in the top-right corner
 */

import { useEffect, useState } from "react";
import { X } from "lucide-react";

export interface ToastProps {
  message: string;
  type?: "info" | "success" | "warning" | "error";
  duration?: number;
  onClose: () => void;
}

export function Toast({ message, type = "info", duration = 4000, onClose }: ToastProps) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(onClose, 300); // Wait for fade out animation
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const bgColorClass = {
    info: "bg-primary/10 border-primary/20",
    success: "bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800",
    warning: "bg-orange-50 dark:bg-orange-950 border-orange-200 dark:border-orange-800",
    error: "bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800",
  }[type];

  const textColorClass = {
    info: "text-primary",
    success: "text-green-800 dark:text-green-200",
    warning: "text-orange-800 dark:text-orange-200",
    error: "text-red-800 dark:text-red-200",
  }[type];

  return (
    <div
      className={`fixed top-4 right-4 z-50 flex items-start gap-3 p-4 rounded-lg border shadow-lg max-w-md transition-all duration-300 ${
        isVisible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-4"
      } ${bgColorClass}`}
    >
      <p className={`text-sm flex-1 ${textColorClass}`}>{message}</p>
      <button
        onClick={() => {
          setIsVisible(false);
          setTimeout(onClose, 300);
        }}
        className={`flex-shrink-0 hover:opacity-70 transition-opacity ${textColorClass}`}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

// Toast container for managing multiple toasts
export interface ToastData {
  id: string;
  message: string;
  type?: "info" | "success" | "warning" | "error";
  duration?: number;
}

interface ToastContainerProps {
  toasts: ToastData[];
  onRemove: (id: string) => void;
}

export function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          duration={toast.duration}
          onClose={() => onRemove(toast.id)}
        />
      ))}
    </div>
  );
}
