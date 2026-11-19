import { Bookmark } from "lucide-react";
import { useState } from "react";
import { ApiError } from "../../api/client";
import { useSaveOpportunity, useSavedOpportunities, useUnsaveOpportunity } from "../../api/queries";
import { useToast } from "../ui/Toast";

/**
 * Save or unsave an opportunity in place. Saving needs a profile (the list
 * belongs to it), so callers render this only for people who have one.
 */
export function SaveToggle({ opportunityId, title, variant = "icon" }: { opportunityId: string; title: string; variant?: "icon" | "button" }) {
  const saved = useSavedOpportunities();
  const save = useSaveOpportunity();
  const unsave = useUnsaveOpportunity();
  const toast = useToast();
  const [pulse, setPulse] = useState(0);
  const isSaved = (saved.data ?? []).some((entry) => entry.opportunity_id === opportunityId);
  const busy = save.isPending || unsave.isPending;

  async function toggle(event: React.MouseEvent) {
    // Rows are links; the toggle must not navigate.
    event.preventDefault();
    event.stopPropagation();
    try {
      if (isSaved) {
        await unsave.mutateAsync(opportunityId);
        toast.show("Removed from your saved list");
      } else {
        await save.mutateAsync({ opportunityId });
        setPulse((value) => value + 1);
        toast.show("Saved. Find it under Saved.");
      }
    } catch (error) {
      toast.show(error instanceof ApiError ? error.message : "That didn’t save. Try again.", "error");
    }
  }

  const icon = <Bookmark key={pulse} size={variant === "icon" ? 18 : 16} className={pulse ? "pop" : ""} fill={isSaved ? "currentColor" : "none"} strokeWidth={1.9} />;

  if (variant === "button") {
    return (
      <button type="button" onClick={toggle} disabled={busy || saved.isPending} aria-pressed={isSaved} className={`btn w-full ${isSaved ? "btn-quiet text-persimmon-deep" : "btn-quiet"}`}>
        {icon}
        {isSaved ? "Saved" : "Save for later"}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy || saved.isPending}
      aria-pressed={isSaved}
      aria-label={isSaved ? `Remove ${title} from saved` : `Save ${title}`}
      title={isSaved ? "Saved" : "Save for later"}
      className={`icon-btn relative z-10 ${isSaved ? "text-persimmon-deep" : "text-muted"}`}
    >
      {icon}
    </button>
  );
}
