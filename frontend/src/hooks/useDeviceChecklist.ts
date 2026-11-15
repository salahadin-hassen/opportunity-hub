import { useCallback, useState } from "react";

const KEY = "oh.confirmations";

function read(): Record<string, boolean> {
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "{}") as Record<string, boolean>;
  } catch {
    return {};
  }
}

/**
 * Ticks a person puts next to conditions they confirmed themselves. Stored only
 * in this browser and never sent to the API: they don't change any verdict.
 */
export function useDeviceChecklist() {
  const [checked, setChecked] = useState<Record<string, boolean>>(read);
  const toggle = useCallback((id: string) => {
    setChecked((old) => {
      const next = { ...old, [id]: !old[id] };
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable: the tick lasts for this visit */
      }
      return next;
    });
  }, []);
  return { checked, toggle };
}
