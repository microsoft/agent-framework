import { useCallback, useEffect, useState } from "react";

import { THEME_STORAGE_KEY } from "../lib/config";

export type ColorScheme = "light" | "dark";

function getInitialScheme(): ColorScheme {
  if (typeof window === "undefined") {
    return "light";
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY) as
    | ColorScheme
    | null;
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function useColorScheme() {
  const [scheme, setScheme] = useState<ColorScheme>(getInitialScheme);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    if (scheme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    window.localStorage.setItem(THEME_STORAGE_KEY, scheme);
  }, [scheme]);

  const toggle = useCallback(() => {
    setScheme((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  const setExplicit = useCallback((value: ColorScheme) => {
    setScheme(value);
  }, []);

  return { scheme, toggle, setScheme: setExplicit };
}
