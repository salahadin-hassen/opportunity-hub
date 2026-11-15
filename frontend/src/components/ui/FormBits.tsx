import { Check, X } from "lucide-react";
import type { ReactNode } from "react";
import type { DegreeLevel, Skill } from "../../api/types";
import { countryOptions } from "../../lib/countries";
import { DEGREE_LABELS, countryName } from "../../lib/format";
import { FieldError } from "./States";

/** States plainly whether the engine reads a field. Never shown on fields it doesn't. */
export function UsageTag({ used }: { used: boolean }) {
  return used ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-cobalt-wash px-1.5 py-px text-[11px] font-medium text-cobalt-deep">
      <Check size={10} strokeWidth={3} />
      Used in eligibility
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-cream px-1.5 py-px text-[11px] text-muted">Stored only</span>
  );
}

export function Field({
  id,
  label,
  used,
  why,
  error,
  optional,
  children,
}: {
  id: string;
  label: string;
  used?: boolean;
  /** One line on why the field is asked for. */
  why?: string;
  error?: string;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <label htmlFor={id} className="text-[13px] font-medium text-ink">
          {label}
          {optional && <span className="ml-1 font-normal text-muted">(optional)</span>}
        </label>
        {used !== undefined && <UsageTag used={used} />}
      </div>
      {children}
      {why && !error && <p className="mt-1.5 text-[12.5px] text-muted">{why}</p>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

export const DEGREE_OPTIONS: DegreeLevel[] = ["high_school", "associate", "bachelor", "master", "doctorate", "other"];

export function DegreeSelect({ id, value, onChange }: { id: string; value: DegreeLevel | ""; onChange: (value: DegreeLevel) => void }) {
  return (
    <select id={id} className="input" value={value} onChange={(event) => onChange(event.target.value as DegreeLevel)} required>
      <option value="" disabled>
        Choose a level
      </option>
      {DEGREE_OPTIONS.map((level) => (
        <option key={level} value={level}>
          {DEGREE_LABELS[level]}
        </option>
      ))}
    </select>
  );
}

export function CountryMulti({ id, values, onChange }: { id: string; values: string[]; onChange: (values: string[]) => void }) {
  return (
    <div>
      <select
        id={id}
        className="input"
        value=""
        onChange={(event) => {
          const code = event.target.value;
          if (code && !values.includes(code)) onChange([...values, code]);
        }}
      >
        <option value="">{values.length ? "Add another country" : "Choose a country"}</option>
        {countryOptions()
          .filter((country) => !values.includes(country.code))
          .map((country) => (
            <option key={country.code} value={country.code}>
              {country.name}
            </option>
          ))}
      </select>
      {values.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {values.map((code) => (
            <li key={code} className="inline-flex h-7 items-center gap-1 rounded-[7px] bg-paper pl-2.5 pr-1 text-[13px] text-ink ring-1 ring-inset ring-rule-strong">
              {countryName(code)}
              <button
                type="button"
                className="inline-flex size-5 items-center justify-center rounded text-muted hover:bg-cream hover:text-ink"
                onClick={() => onChange(values.filter((value) => value !== code))}
                aria-label={`Remove ${countryName(code)}`}
              >
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SkillPicker({
  catalog,
  selected,
  onToggle,
  disabled,
}: {
  catalog: Skill[];
  selected: Set<string>;
  onToggle: (skill: Skill) => void;
  disabled?: boolean;
}) {
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Skills">
      {catalog.map((skill) => {
        const active = selected.has(skill.id);
        return (
          <li key={skill.id}>
            <button
              type="button"
              aria-pressed={active}
              disabled={disabled}
              onClick={() => onToggle(skill)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-[7px] px-2.5 text-[13.5px] transition-colors duration-150 ${
                active ? "bg-ink text-on-ink" : "bg-paper text-ink ring-1 ring-inset ring-rule-strong hover:ring-faint"
              }`}
            >
              {active && <Check size={13} strokeWidth={2.6} />}
              {skill.name}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function Toggle({ id, checked, onChange, label }: { id: string; checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-3 rounded-md text-[14px] text-ink"
    >
      <span className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-200 ${checked ? "bg-cobalt" : "bg-rule-strong"}`}>
        <span className={`absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform duration-200 ${checked ? "translate-x-[18px]" : "translate-x-0.5"}`} />
      </span>
      {label}
    </button>
  );
}
