import { ChevronLeft, ChevronRight } from "lucide-react";

/** Pages shown around the current one, with gaps collapsed: 1 … 4 5 6 … 14. */
function pageList(page: number, count: number): (number | "gap")[] {
  const wanted = new Set([1, count, page - 1, page, page + 1].filter((value) => value >= 1 && value <= count));
  const sorted = [...wanted].sort((a, b) => a - b);
  const out: (number | "gap")[] = [];
  sorted.forEach((value, index) => {
    if (index > 0 && value - sorted[index - 1]! > 1) out.push("gap");
    out.push(value);
  });
  return out;
}

export function Pagination({ page, pageCount, onChange, label = "Pages" }: { page: number; pageCount: number; onChange: (page: number) => void; label?: string }) {
  if (pageCount <= 1) return null;
  const step = "inline-flex h-10 min-w-10 items-center justify-center rounded-full px-3 text-[14px] transition-colors";
  return (
    <nav aria-label={label} className="flex items-center justify-between gap-2 sm:justify-center">
      <button type="button" className={`${step} gap-1 text-ink-soft hover:bg-cream hover:text-ink disabled:opacity-35`} onClick={() => onChange(page - 1)} disabled={page <= 1}>
        <ChevronLeft size={16} />
        <span>Previous</span>
      </button>
      <ol className="hidden items-center gap-1 sm:flex">
        {pageList(page, pageCount).map((value, index) =>
          value === "gap" ? (
            <li key={`gap-${index}`} className="px-1 text-faint" aria-hidden="true">
              …
            </li>
          ) : (
            <li key={value}>
              <button
                type="button"
                onClick={() => onChange(value)}
                aria-current={value === page ? "page" : undefined}
                aria-label={`Page ${value}`}
                className={`${step} num ${value === page ? "bg-ink font-semibold text-paper" : "text-ink-soft hover:bg-cream hover:text-ink"}`}
              >
                {value}
              </button>
            </li>
          ),
        )}
      </ol>
      <span className="num text-[13.5px] text-muted sm:hidden">
        Page {page} of {pageCount}
      </span>
      <button type="button" className={`${step} gap-1 text-ink-soft hover:bg-cream hover:text-ink disabled:opacity-35`} onClick={() => onChange(page + 1)} disabled={page >= pageCount}>
        <span>Next</span>
        <ChevronRight size={16} />
      </button>
    </nav>
  );
}
