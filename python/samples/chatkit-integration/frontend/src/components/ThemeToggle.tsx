import clsx from "clsx";
import { Moon, Sun } from "lucide-react";

import type { ColorScheme } from "../hooks/useColorScheme";

type ThemeToggleProps = {
  value: ColorScheme;
  onChange: (scheme: ColorScheme) => void;
};

const buttonBase =
  "inline-flex h-9 w-9 items-center justify-center rounded-full text-[0.7rem] transition-colors duration-200";

export function ThemeToggle({ value, onChange }: ThemeToggleProps) {
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white/60 p-1 shadow-sm backdrop-blur-sm dark:border-slate-800 dark:bg-slate-900/60">
      <button
        type="button"
        onClick={() => onChange("light")}
        className={clsx(
          buttonBase,
          value === "light"
            ? "bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900"
            : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100",
        )}
        aria-label="Use light theme"
        aria-pressed={value === "light"}
      >
        <Sun className="h-4 w-4" aria-hidden />
      </button>
      <button
        type="button"
        onClick={() => onChange("dark")}
        className={clsx(
          buttonBase,
          value === "dark"
            ? "bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900"
            : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100",
        )}
        aria-label="Use dark theme"
        aria-pressed={value === "dark"}
      >
        <Moon className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
