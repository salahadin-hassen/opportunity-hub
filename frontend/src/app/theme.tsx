import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";

/** localStorage key; index.html reads the same key before first paint. */
export const THEME_KEY = "oh.theme";

const THEME_COLOR: Record<Theme, string> = { light: "#F5F2E9", dark: "#12151B" };

function current(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function apply(theme: Theme, animate: boolean) {
  const root = document.documentElement;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (animate && !reduced) {
    root.classList.add("theme-switching");
    window.setTimeout(() => root.classList.remove("theme-switching"), 320);
  }
  if (theme === "dark") root.dataset.theme = "dark";
  else delete root.dataset.theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
}

type ThemeState = { theme: Theme; setTheme: (theme: Theme) => void; toggle: () => void };

const ThemeContext = createContext<ThemeState | null>(null);

/**
 * Light is the default. An explicit choice is remembered in localStorage; if
 * storage is unavailable the choice lasts for the visit and new visits are light.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setState] = useState<Theme>(current);

  const setTheme = useCallback((next: Theme) => {
    apply(next, true);
    setState(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      /* storage unavailable: keep the choice for this visit only */
    }
  }, []);

  const toggle = useCallback(() => setTheme(current() === "dark" ? "light" : "dark"), [setTheme]);
  const value = useMemo(() => ({ theme, setTheme, toggle }), [theme, setTheme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside <ThemeProvider>");
  return value;
}
