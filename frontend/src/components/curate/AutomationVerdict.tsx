import { Bot, CheckCircle2, XCircle } from "lucide-react";

type Autonomy = {
  mode: string;
  outcome: string;
  acted: string;
  decided_at: string;
  checks: { name: string; passed: boolean; detail: string }[];
  title?: string | null;
  deadline?: string | null;
  ai?: { model?: string; confidence?: number; concerns?: string[]; dropped?: string[] } | null;
};

const ACTED: Record<string, string> = {
  published: "Published automatically",
  drafted: "Drafted automatically",
  held: "Held for a person",
  "would publish": "Shadow: would have published",
  "would draft": "Shadow: would have drafted",
};

/** What the autonomous reviewer decided about this candidate, check by check (only for sources above "off"). */
export function AutomationVerdict({ validation }: { validation: unknown }) {
  const autonomy = (validation as { autonomy?: Autonomy } | null)?.autonomy;
  if (!autonomy) return null;
  const failed = autonomy.checks.filter((check) => !check.passed);
  return (
    <section aria-label="Automatic review" className="space-y-3 rounded-panel border border-rule bg-paper p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-2 text-[15px] font-bold text-ink">
          <Bot size={16} aria-hidden="true" /> Automatic review
        </h3>
        <span className={`text-[13px] font-semibold ${failed.length ? "text-potential-ink" : "text-eligible-ink"}`}>{ACTED[autonomy.acted] ?? autonomy.acted}</span>
      </div>
      <ul className="space-y-1.5 text-[13px]">
        {autonomy.checks.map((check) => (
          <li key={check.name} className="flex items-start gap-2">
            {check.passed ? (
              <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-eligible" aria-label="passed" />
            ) : (
              <XCircle size={15} className="mt-0.5 shrink-0 text-ineligible" aria-label="failed" />
            )}
            <span className={check.passed ? "text-ink-soft" : "text-ink"}>
              <span className="font-semibold">{check.name.charAt(0).toUpperCase() + check.name.slice(1)}</span>
              {!check.passed && <>: {check.detail}</>}
            </span>
          </li>
        ))}
      </ul>
      {autonomy.ai && (
        <p className="text-[12.5px] text-muted">
          AI review ({autonomy.ai.model}), confidence {Math.round((autonomy.ai.confidence ?? 0) * 100)}%.
          {autonomy.ai.concerns?.length ? ` Concerns: ${autonomy.ai.concerns.join("; ")}` : ""}
          {autonomy.ai.dropped?.length ? ` ${autonomy.ai.dropped.length} AI answer(s) were dropped because the page doesn’t say them.` : ""}
        </p>
      )}
      <p className="text-[12px] text-muted">
        Source automation: {autonomy.mode.replace("_", " ")} · decided {new Date(autonomy.decided_at).toLocaleString()}
      </p>
    </section>
  );
}
