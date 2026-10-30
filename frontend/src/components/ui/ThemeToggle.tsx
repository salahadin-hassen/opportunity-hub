import { AnimatePresence, motion } from "motion/react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "../../app/theme";

/** Sun in light, moon in dark: the icon shows the active theme; the switch state says the same to assistive tech. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Dark theme"
      title={dark ? "Dark theme is on" : "Dark theme is off"}
      onClick={toggle}
      className={`relative inline-flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full text-ink-soft transition-colors duration-150 hover:bg-cream hover:text-ink ${className}`}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ rotate: -60, scale: 0.6, opacity: 0 }}
          animate={{ rotate: 0, scale: 1, opacity: 1 }}
          exit={{ rotate: 60, scale: 0.6, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className="inline-flex"
        >
          {dark ? <Moon size={18} strokeWidth={1.9} /> : <Sun size={18} strokeWidth={1.9} />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
