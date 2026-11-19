import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

/**
 * A modal sheet on the native <dialog>: the browser traps focus, closes on
 * Escape and makes the page behind it inert. Bottom on phones, side or centre
 * elsewhere. Clicking the backdrop closes it.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
  placement = "bottom",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  placement?: "bottom" | "right" | "center";
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`sheet-dialog sheet-${placement}`}
      aria-labelledby="sheet-title"
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="flex h-full max-h-[inherit] flex-col">
        <div className="flex items-center justify-between border-b border-rule px-5 py-3.5">
          <h2 id="sheet-title" className="heading text-[19px] text-ink">
            {title}
          </h2>
          <button type="button" className="icon-btn -mr-2" onClick={onClose} aria-label="Close">
            <X size={19} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>
        {footer && <div className="border-t border-rule px-5 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))]">{footer}</div>}
      </div>
    </dialog>
  );
}
