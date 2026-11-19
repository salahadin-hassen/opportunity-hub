import { AlertTriangle, Loader2, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function Spinner({ size = 16, className = "" }: { size?: number; className?: string }) {
  return <Loader2 size={size} className={`animate-spin ${className}`} aria-hidden="true" />;
}

/** An empty or no-results state: says what's missing, why, and the next useful step. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mt-6 flex flex-col items-center rounded-panel border border-dashed border-rule-strong px-6 py-14 text-center sm:px-10">
      <span className="mb-5 inline-flex size-12 items-center justify-center rounded-full border border-rule-strong bg-paper text-ink-soft">
        <Icon size={20} strokeWidth={1.7} />
      </span>
      <p className="heading text-[21px] text-ink">{title}</p>
      {children && <div className="mt-2 max-w-[46ch] text-[14.5px] leading-relaxed text-ink-soft">{children}</div>}
      {action && <div className="mt-6 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-panel border border-ineligible/30 bg-ineligible-wash px-4 py-3 text-[14px] text-ineligible-ink">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <div className="flex-1">{message}</div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-medium underline underline-offset-2">
          Try again
        </button>
      )}
    </div>
  );
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1.5 text-[13px] text-ineligible-ink">
      {message}
    </p>
  );
}
