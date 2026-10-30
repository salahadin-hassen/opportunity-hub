import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type Toast = { id: number; message: string; tone: "ok" | "error" };
type ToastApi = { show: (message: string, tone?: Toast["tone"]) => void };

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(0);
  const show = useCallback((message: string, tone: Toast["tone"] = "ok") => {
    const id = ++next.current;
    setToasts((all) => [...all.slice(-2), { id, message, tone }]);
    window.setTimeout(() => setToasts((all) => all.filter((toast) => toast.id !== id)), 3800);
  }, []);
  const value = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-5 z-[60] flex flex-col items-center gap-2 px-4">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              layout
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 6, scale: 0.98 }}
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              className="pointer-events-auto flex max-w-md items-center gap-2.5 rounded-[10px] bg-toast px-3.5 py-2.5 text-[14px] text-toast-text shadow-float ring-1 ring-toast-edge"
            >
              {toast.tone === "ok" ? (
                <CheckCircle2 size={16} className="text-lime" />
              ) : (
                <AlertTriangle size={16} className="text-ineligible" />
              )}
              {toast.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside <ToastProvider>");
  return value;
}
