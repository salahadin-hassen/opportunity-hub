import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, CalendarDays, Flag, GraduationCap, Sparkles } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { ApiError } from "../../api/client";
import { useEducation, useOpportunities, useProfile, useSaveEducation, useUpdateProfile } from "../../api/queries";
import type { Match, MatchStatus } from "../../api/types";
import { useEligibility } from "../../features/eligibility";
import { countryOptions } from "../../lib/countries";
import { plural } from "../../lib/format";
import { affectedOpportunities, missingFactImpacts, type FactImpact } from "../../lib/resolve";
import { FACT_LABELS, FACT_NOUNS, type Fact } from "../../lib/rules";
import { FieldError, Spinner } from "../ui/States";
import { useToast } from "../ui/Toast";
import { VerdictBadge } from "../ui/Verdict";
import { FACT_ANCHOR } from "./Evidence";

const FACT_ICON: Partial<Record<Fact, typeof CalendarDays>> = {
  date_of_birth: CalendarDays,
  gpa: GraduationCap,
  citizenship: Flag,
};

export type Change = { id: string; title: string; from: MatchStatus; to: MatchStatus };

function useTitles() {
  const opportunities = useOpportunities();
  return (id: string) => opportunities.data?.find((item) => item.id === id)?.title ?? "Opportunity";
}

/** Save one fact, re-run only the opportunities it affects, and report verdict changes. */
function useResolve(impact: FactImpact, onChanges: (changes: Change[]) => void) {
  const { run } = useEligibility();
  const titleOf = useTitles();
  const toast = useToast();
  return async (save: () => Promise<unknown>, statuses: Map<string, MatchStatus>) => {
    await save();
    const ids = affectedOpportunities(impact);
    const results: Match[] = await run(ids);
    const changes = results
      .filter((match) => statuses.get(match.opportunity_id) && statuses.get(match.opportunity_id) !== match.status)
      .map((match) => ({
        id: match.opportunity_id,
        title: titleOf(match.opportunity_id),
        from: statuses.get(match.opportunity_id)!,
        to: match.status,
      }));
    onChanges(changes);
    toast.show(
      changes.length
        ? `${plural(changes.length, "verdict")} changed`
        : `Re-checked ${plural(ids.length, "opportunity", "opportunities")}`,
    );
  };
}

function FactForm({ impact, matches, onChanges }: { impact: FactImpact; matches: Match[]; onChanges: (changes: Change[]) => void }) {
  const profile = useProfile();
  const education = useEducation();
  const updateProfile = useUpdateProfile();
  const saveEducation = useSaveEducation();
  const resolve = useResolve(impact, onChanges);
  const { running } = useEligibility();
  const [value, setValue] = useState("");
  const [scale, setScale] = useState("4");
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const primary = education.data?.find((item) => item.is_primary);
  const fieldId = `resolve-${impact.fact}`;

  const statuses = new Map(matches.map((match) => [match.opportunity_id, match.status]));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(undefined);
    if (!value) {
      setError("Enter a value first.");
      return;
    }
    setBusy(true);
    try {
      await resolve(async () => {
        if (impact.fact === "date_of_birth") {
          await updateProfile.mutateAsync({ date_of_birth: value });
        } else if (impact.fact === "citizenship") {
          const existing = profile.data?.citizenships ?? [];
          await updateProfile.mutateAsync({ citizenships: [...new Set([...existing, value])] });
        } else if (impact.fact === "gpa" && primary) {
          const gpa = Number(value);
          if (!Number.isFinite(gpa) || gpa < 0 || gpa > Number(scale)) {
            throw new ApiError(422, `Enter a GPA between 0 and ${scale}.`);
          }
          await saveEducation.mutateAsync({ id: primary.id, body: { gpa, gpa_scale: Number(scale) } });
        }
      }, statuses);
      setValue("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Couldn’t save. Try again.");
    } finally {
      setBusy(false);
    }
  }

  let control: ReactNode;
  if (impact.fact === "date_of_birth") {
    control = (
      <input
        id={fieldId}
        type="date"
        className="input"
        value={value}
        max={new Date().toISOString().slice(0, 10)}
        onChange={(event) => setValue(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${fieldId}-error` : undefined}
      />
    );
  } else if (impact.fact === "citizenship") {
    control = (
      <select id={fieldId} className="input" value={value} onChange={(event) => setValue(event.target.value)} aria-invalid={Boolean(error)}>
        <option value="">Choose a country</option>
        {countryOptions().map((country) => (
          <option key={country.code} value={country.code}>
            {country.name}
          </option>
        ))}
      </select>
    );
  } else if (impact.fact === "gpa") {
    if (!primary) {
      return (
        <p className="text-[13.5px] text-muted">
          GPA is stored on your primary education record.{" "}
          <Link to={FACT_ANCHOR.gpa} className="font-medium text-cobalt-deep hover:underline">
            Add your education
          </Link>{" "}
          first.
        </p>
      );
    }
    control = (
      <div className="flex gap-2">
        <input
          id={fieldId}
          type="number"
          inputMode="decimal"
          step="0.01"
          min={0}
          max={Number(scale)}
          placeholder="3.72"
          className="input num flex-1"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={`${fieldId}-hint`}
        />
        <label className="sr-only" htmlFor={`${fieldId}-scale`}>
          GPA scale
        </label>
        <select id={`${fieldId}-scale`} className="input w-28" value={scale} onChange={(event) => setScale(event.target.value)}>
          <option value="4">of 4.0</option>
          <option value="5">of 5.0</option>
          <option value="10">of 10</option>
          <option value="100">of 100</option>
        </select>
      </div>
    );
  } else {
    return (
      <Link to={FACT_ANCHOR[impact.fact]} className="btn btn-quiet btn-sm">
        Edit in profile
      </Link>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor={fieldId} className="sr-only">
        {FACT_LABELS[impact.fact]}
      </label>
      <div className="flex flex-col gap-2">
        {control}
        <button type="submit" className="btn btn-primary h-10 w-full" disabled={busy || running}>
          {busy ? <Spinner size={14} /> : null}
          {busy ? "Re-checking" : "Save and re-check"}
        </button>
      </div>
      {impact.fact === "gpa" && (
        <p id={`${fieldId}-hint`} className="text-[12.5px] text-muted">
          Thresholds are compared only on the scale they were published on. A GPA on another scale is sent to your review rather than converted.
        </p>
      )}
      <FieldError id={`${fieldId}-error`} message={error} />
    </form>
  );
}

function ImpactCard({ impact, matches, onChanges }: { impact: FactImpact; matches: Match[]; onChanges: (changes: Change[]) => void }) {
  const titleOf = useTitles();
  const Icon = FACT_ICON[impact.fact] ?? Sparkles;
  const decisive = impact.decisive.length;
  const all = affectedOpportunities(impact);
  return (
    <div className="sheet p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-potential-wash text-potential-ink">
          <Icon size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-medium text-ink">Add your {FACT_NOUNS[impact.fact]}</p>
          <p className="mt-0.5 text-[13.5px] text-muted">
            {decisive > 0
              ? `It’s the only missing fact for ${plural(decisive, "opportunity", "opportunities")}, so adding it settles ${decisive === 1 ? "that verdict" : "those verdicts"}.`
              : `Rules in ${plural(all.length, "opportunity", "opportunities")} read it. Other conditions still decide ${all.length === 1 ? "that verdict" : "those verdicts"}.`}
          </p>
          <ul className="mt-2.5 flex flex-col gap-1 border-l border-rule pl-3">
            {all.map((id) => (
              <li key={id} className="flex items-baseline gap-2 text-[13px]">
                <Link to={`/opportunities/${id}`} className="min-w-0 text-ink hover:text-cobalt-deep hover:underline">
                  {titleOf(id)}
                </Link>
                {impact.decisive.includes(id) && <span className="shrink-0 text-[12px] font-medium text-potential-ink">settles it</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="mt-4">
        <FactForm impact={impact} matches={matches} onChanges={onChanges} />
      </div>
    </div>
  );
}

export function ChangeSummary({ changes, onDismiss }: { changes: Change[]; onDismiss: () => void }) {
  return (
    <AnimatePresence>
      {changes.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden rounded-panel border border-cobalt/30 bg-paper shadow-float"
          role="status"
        >
          <div className="flex items-center justify-between border-b border-rule bg-cobalt-wash/60 px-4 py-2.5">
            <p className="text-[13.5px] font-medium text-ink">Your update changed {plural(changes.length, "verdict")}</p>
            <button type="button" onClick={onDismiss} className="text-[13px] text-muted hover:text-ink">
              Dismiss
            </button>
          </div>
          <ul className="divide-y divide-rule">
            {changes.map((change, index) => (
              <motion.li
                key={change.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.12 + index * 0.08, duration: 0.25 }}
                className="flex flex-col gap-2 px-4 py-3"
              >
                <Link to={`/opportunities/${change.id}`} className="text-[14px] font-medium text-ink hover:underline">
                  {change.title}
                </Link>
                <div className="flex items-center gap-2">
                  <span className="opacity-60">
                    <VerdictBadge status={change.from} size="sm" />
                  </span>
                  <ArrowRight size={14} className="text-faint" aria-label="changed to" />
                  <VerdictBadge status={change.to} size="sm" animateKey={`${change.id}-${change.to}`} />
                </div>
              </motion.li>
            ))}
          </ul>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Missing profile facts, most decisive first, each with an inline way to add it. */
export function ResolvePanel({ matches, onChanges }: { matches: Match[]; onChanges: (changes: Change[]) => void }) {
  const impacts = missingFactImpacts(matches);
  if (impacts.length === 0) return null;
  return (
    <section aria-labelledby="resolve-title" className="flex flex-col gap-3">
      <div>
        <h2 id="resolve-title" className="heading text-[18px] text-ink">
          Fill the gaps
        </h2>
        <p className="mt-1 text-[14px] text-muted">
          These facts are missing from your profile, and published rules depend on them. Add one and the affected opportunities are checked again straight away.
        </p>
      </div>
      {impacts.map((impact) => (
        <ImpactCard key={impact.fact} impact={impact} matches={matches} onChanges={onChanges} />
      ))}
    </section>
  );
}
