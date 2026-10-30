import { AnimatePresence, motion } from "motion/react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ApiError } from "../api/client";
import {
  useAddTestScore,
  useDeleteTestScore,
  useEducation,
  useMySkills,
  useProfile,
  useSaveEducation,
  useSkillCatalog,
  useTestScores,
  useToggleSkill,
  useUpdateProfile,
} from "../api/queries";
import type { DegreeLevel, Education, Profile as ProfileData } from "../api/types";
import { PageHeader } from "../components/layout/AppShell";
import { Content, Page } from "../components/layout/Page";
import { CountryMulti, DegreeSelect, Field, SkillPicker, Toggle, UsageTag } from "../components/ui/FormBits";
import { ErrorState, Spinner } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { useEligibility } from "../features/eligibility";
import { countryOptions } from "../lib/countries";
import { formatPlainDate } from "../lib/format";
import { FACT_LABELS, type Fact } from "../lib/rules";

function Section({ id, title, description, children }: { id: string; title: string; description: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20 grid grid-cols-1 gap-4 border-t border-rule pt-8 lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-10">
      <div>
        <h2 id={`${id}-title`} className="heading text-[17px] text-ink">
          {title}
        </h2>
        <p className="mt-1 text-[13.5px] text-muted">{description}</p>
      </div>
      <div>{children}</div>
    </section>
  );
}

function SaveBar({ busy, dirty, error }: { busy: boolean; dirty: boolean; error?: string | null }) {
  return (
    <div className="flex items-center justify-end gap-3 border-t border-rule bg-tint px-5 py-3">
      {error && <p className="mr-auto text-[13px] text-ineligible-ink">{error}</p>}
      <button type="submit" className="btn btn-ink btn-sm" disabled={busy || !dirty}>
        {busy && <Spinner size={13} />}
        Save changes
      </button>
    </div>
  );
}

/** Only facts the engine reads count towards completeness. */
function completeness(profile: ProfileData, primary: Education | undefined, skillCount: number): { fact: Fact; done: boolean }[] {
  return [
    { fact: "citizenship", done: profile.citizenships.length > 0 },
    { fact: "date_of_birth", done: Boolean(profile.date_of_birth) },
    { fact: "degree_level", done: Boolean(profile.degree_level) },
    { fact: "enrollment", done: true },
    { fact: "gpa", done: primary?.gpa != null },
    { fact: "skills", done: skillCount > 0 },
  ];
}

function Completeness({ items }: { items: { fact: Fact; done: boolean }[] }) {
  const done = items.filter((item) => item.done).length;
  return (
    <div className="sheet p-5">
      <div className="flex items-baseline justify-between">
        <p className="text-[14px] font-medium text-ink">Eligibility facts</p>
        <p className="num text-[13px] text-muted">
          {done}/{items.length}
        </p>
      </div>
      <div className="mt-3 flex gap-1" aria-hidden="true">
        {items.map((item) => (
          <motion.span
            key={item.fact}
            className="h-1.5 flex-1 rounded-full"
            initial={false}
            animate={{ backgroundColor: item.done ? "var(--color-cobalt)" : "var(--color-rule)" }}
            transition={{ duration: 0.3 }}
          />
        ))}
      </div>
      <ul className="mt-4 grid grid-cols-1 gap-1.5 text-[13px] sm:grid-cols-2">
        {items.map((item) => (
          <li key={item.fact} className={`flex items-center gap-2 ${item.done ? "text-ink" : "text-muted"}`}>
            <span className={`size-1.5 rounded-full ${item.done ? "bg-cobalt" : "border border-faint"}`} />
            {FACT_LABELS[item.fact]}
            {!item.done && <span className="text-potential-ink">missing</span>}
          </li>
        ))}
      </ul>
      <p className="mt-4 text-[12.5px] text-muted">Only facts that published rules read are counted. Missing ones leave matching rules undecided.</p>
    </div>
  );
}

function IdentityForm({ profile }: { profile: ProfileData }) {
  const update = useUpdateProfile();
  const { markStale } = useEligibility();
  const toast = useToast();
  const initial = {
    full_name: profile.full_name,
    email: profile.email,
    date_of_birth: profile.date_of_birth ?? "",
    citizenships: profile.citizenships,
    country_of_residence: profile.country_of_residence ?? "",
  };
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setForm(initial), [profile.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(form) !== JSON.stringify(initial);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setErrors({});
    setError(null);
    try {
      await update.mutateAsync({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        date_of_birth: form.date_of_birth || null,
        citizenships: form.citizenships,
        country_of_residence: form.country_of_residence || null,
      });
      if (form.date_of_birth !== initial.date_of_birth || form.citizenships.join() !== initial.citizenships.join()) markStale();
      toast.show("Profile saved");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setErrors(caught.fields);
        setError(caught.message);
      } else setError("Couldn’t save. Try again.");
    }
  }

  return (
    <form onSubmit={submit} className="sheet overflow-hidden" noValidate>
      <div className="grid grid-cols-1 gap-5 p-5 sm:grid-cols-2">
        <Field id="p-name" label="Full name" error={errors.full_name}>
          <input id="p-name" className="input" value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
        </Field>
        <Field id="p-email" label="Contact email" error={errors.email}>
          <input id="p-email" type="email" className="input" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
        </Field>
        <Field id="p-dob" label="Date of birth" used error={errors.date_of_birth} why="Checked against age limits.">
          <input
            id="p-dob"
            type="date"
            className="input"
            max={new Date().toISOString().slice(0, 10)}
            value={form.date_of_birth}
            onChange={(event) => setForm({ ...form, date_of_birth: event.target.value })}
          />
        </Field>
        <Field id="p-residence" label="Country of residence" used={false}>
          <select id="p-residence" className="input" value={form.country_of_residence} onChange={(event) => setForm({ ...form, country_of_residence: event.target.value })}>
            <option value="">Not set</option>
            {countryOptions().map((country) => (
              <option key={country.code} value={country.code}>
                {country.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field id="p-citizenship" label="Citizenship" used why="Add every citizenship you hold.">
            <CountryMulti id="p-citizenship" values={form.citizenships} onChange={(values) => setForm({ ...form, citizenships: values })} />
          </Field>
        </div>
      </div>
      <SaveBar busy={update.isPending} dirty={dirty} error={error} />
    </form>
  );
}

function AcademicForm({ profile }: { profile: ProfileData }) {
  const update = useUpdateProfile();
  const { markStale } = useEligibility();
  const toast = useToast();
  const [degree, setDegree] = useState<DegreeLevel>(profile.degree_level);
  const [enrolled, setEnrolled] = useState(profile.is_currently_enrolled);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setDegree(profile.degree_level);
    setEnrolled(profile.is_currently_enrolled);
  }, [profile.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = degree !== profile.degree_level || enrolled !== profile.is_currently_enrolled;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({ degree_level: degree, is_currently_enrolled: enrolled });
      markStale();
      toast.show("Academic status saved");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Couldn’t save. Try again.");
    }
  }

  return (
    <form onSubmit={submit} className="sheet overflow-hidden">
      <div className="grid grid-cols-1 gap-5 p-5 sm:grid-cols-2">
        <Field id="p-degree" label="Current degree level" used why="Matched against degree requirements.">
          <DegreeSelect id="p-degree" value={degree} onChange={setDegree} />
        </Field>
        <Field id="p-enrolled" label="Enrolment" used>
          <div className="flex h-10 items-center">
            <Toggle id="p-enrolled" checked={enrolled} onChange={setEnrolled} label="I’m currently enrolled" />
          </div>
        </Field>
      </div>
      <SaveBar busy={update.isPending} dirty={dirty} error={error} />
    </form>
  );
}

function EducationForm({ profile, primary }: { profile: ProfileData; primary: Education | undefined }) {
  const save = useSaveEducation();
  const { markStale } = useEligibility();
  const toast = useToast();
  const initial = {
    institution_name: primary?.institution_name ?? "",
    field_of_study: primary?.field_of_study ?? "",
    gpa: primary?.gpa != null ? String(primary.gpa) : "",
    gpa_scale: primary?.gpa_scale != null ? String(primary.gpa_scale) : "4",
  };
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setForm(initial), [primary?.id, primary?.gpa, primary?.gpa_scale]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(form) !== JSON.stringify(initial);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!form.institution_name.trim()) next.institution_name = "Enter your institution.";
    if (!form.field_of_study.trim()) next.field_of_study = "Enter your field of study.";
    if (form.gpa) {
      const gpa = Number(form.gpa);
      if (!Number.isFinite(gpa) || gpa < 0 || gpa > Number(form.gpa_scale)) next.gpa = `Enter a GPA between 0 and ${form.gpa_scale}.`;
    }
    setErrors(next);
    setError(null);
    if (Object.keys(next).length) return;
    const gpa = form.gpa ? { gpa: Number(form.gpa), gpa_scale: Number(form.gpa_scale) } : { gpa: null, gpa_scale: null };
    try {
      await save.mutateAsync(
        primary
          ? { id: primary.id, body: { institution_name: form.institution_name.trim(), field_of_study: form.field_of_study.trim(), ...gpa } }
          : {
              body: {
                institution_name: form.institution_name.trim(),
                field_of_study: form.field_of_study.trim(),
                degree_level: profile.degree_level,
                is_current: profile.is_currently_enrolled,
                is_primary: true,
                ...gpa,
              },
            },
      );
      if (form.gpa !== initial.gpa || form.gpa_scale !== initial.gpa_scale) markStale();
      toast.show("Education saved");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setErrors(caught.fields);
        setError(caught.message);
      } else setError("Couldn’t save. Try again.");
    }
  }

  return (
    <form onSubmit={submit} className="sheet overflow-hidden" noValidate>
      <div className="grid grid-cols-1 gap-5 p-5 sm:grid-cols-2">
        <Field id="e-inst" label="Institution" used={false} error={errors.institution_name}>
          <input id="e-inst" className="input" value={form.institution_name} onChange={(event) => setForm({ ...form, institution_name: event.target.value })} />
        </Field>
        <Field id="e-field" label="Field of study" used={false} error={errors.field_of_study}>
          <input id="e-field" className="input" value={form.field_of_study} onChange={(event) => setForm({ ...form, field_of_study: event.target.value })} />
        </Field>
        <div className="sm:col-span-2">
          <Field
            id="e-gpa"
            label="GPA"
            used
            optional
            error={errors.gpa}
            why="Compared only with thresholds published on the same scale. Clear it to remove your GPA."
          >
            <div className="flex max-w-[360px] gap-2">
              <input id="e-gpa" type="number" step="0.01" min={0} inputMode="decimal" className="input num flex-1" value={form.gpa} onChange={(event) => setForm({ ...form, gpa: event.target.value })} />
              <label htmlFor="e-scale" className="sr-only">
                GPA scale
              </label>
              <select id="e-scale" className="input w-28" value={form.gpa_scale} onChange={(event) => setForm({ ...form, gpa_scale: event.target.value })}>
                <option value="4">of 4.0</option>
                <option value="5">of 5.0</option>
                <option value="10">of 10</option>
                <option value="100">of 100</option>
              </select>
            </div>
          </Field>
        </div>
      </div>
      <SaveBar busy={save.isPending} dirty={dirty} error={error} />
    </form>
  );
}

function SkillsEditor() {
  const catalog = useSkillCatalog();
  const mine = useMySkills();
  const toggle = useToggleSkill();
  const { markStale } = useEligibility();
  const toast = useToast();
  const selected = new Set((mine.data ?? []).map((skill) => skill.id));
  if (catalog.isError || mine.isError) return <ErrorState message="Skills couldn’t load." onRetry={() => { catalog.refetch(); mine.refetch(); }} />;
  return (
    <div className="sheet p-5">
      {catalog.isPending || mine.isPending ? (
        <div className="flex flex-wrap gap-1.5">
          {Array.from({ length: 10 }, (_, index) => (
            <div key={index} className="skeleton h-8 w-24" />
          ))}
        </div>
      ) : (
        <SkillPicker
          catalog={catalog.data}
          selected={selected}
          disabled={toggle.isPending}
          onToggle={(skill) =>
            toggle.mutate(
              { skillId: skill.id, attached: selected.has(skill.id) },
              {
                onSuccess: () => markStale(),
                onError: (caught) => toast.show(caught instanceof ApiError ? caught.message : "Couldn’t update skills.", "error"),
              },
            )
          }
        />
      )}
    </div>
  );
}

function TestScores() {
  const scores = useTestScores();
  const add = useAddTestScore();
  const remove = useDeleteTestScore();
  const [form, setForm] = useState({ test_type: "", overall_score: "", test_date: "" });
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!form.test_type.trim() || form.overall_score === "" || Number(form.overall_score) < 0) {
      setError("Enter a test name and a score of 0 or more.");
      return;
    }
    try {
      await add.mutateAsync({ test_type: form.test_type.trim(), overall_score: Number(form.overall_score), test_date: form.test_date || null });
      setForm({ test_type: "", overall_score: "", test_date: "" });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Couldn’t add the score.");
    }
  }

  return (
    <div className="sheet overflow-hidden">
      <AnimatePresence initial={false}>
        {(scores.data ?? []).length > 0 && (
          <ul className="divide-y divide-rule">
            {scores.data!.map((score) => (
              <motion.li key={score.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-4 px-5 py-3">
                <span className="flex-1 text-[14px] text-ink">{score.test_type}</span>
                <span className="num text-[13px] text-ink">{score.overall_score}</span>
                <span className="num w-28 text-right text-[12.5px] text-muted">{score.test_date ? formatPlainDate(score.test_date) : "No date"}</span>
                <button type="button" className="btn btn-ghost btn-sm px-1.5" aria-label={`Remove ${score.test_type}`} onClick={() => remove.mutate(score.id)}>
                  <Trash2 size={14} />
                </button>
              </motion.li>
            ))}
          </ul>
        )}
      </AnimatePresence>
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 border-t border-rule bg-tint p-5 first:border-t-0 sm:grid-cols-[minmax(0,1fr)_110px_150px_auto] sm:items-end">
        <div>
          <label htmlFor="t-type" className="field-label">
            Test
          </label>
          <input id="t-type" className="input" placeholder="IELTS Academic" value={form.test_type} onChange={(event) => setForm({ ...form, test_type: event.target.value })} />
        </div>
        <div>
          <label htmlFor="t-score" className="field-label">
            Score
          </label>
          <input id="t-score" type="number" step="0.1" min={0} className="input num" value={form.overall_score} onChange={(event) => setForm({ ...form, overall_score: event.target.value })} />
        </div>
        <div>
          <label htmlFor="t-date" className="field-label">
            Date
          </label>
          <input id="t-date" type="date" className="input" value={form.test_date} onChange={(event) => setForm({ ...form, test_date: event.target.value })} />
        </div>
        <button type="submit" className="btn btn-quiet h-10" disabled={add.isPending}>
          <Plus size={15} />
          Add
        </button>
        {error && <p className="text-[13px] text-ineligible-ink sm:col-span-4">{error}</p>}
      </form>
    </div>
  );
}

export function Profile() {
  const profile = useProfile();
  const education = useEducation();
  const mySkills = useMySkills();
  const { stale, run, running, progress } = useEligibility();
  const toast = useToast();
  const data = profile.data!;
  const primary = education.data?.find((item) => item.is_primary);

  return (
    <Page title="Profile">
      <Content>
        <PageHeader title="Profile" description="Edit the facts your verdicts are based on. Changes take effect the next time you run a check." />

        <AnimatePresence>
          {stale && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="sticky top-16 z-20 mt-6 flex items-center gap-3 rounded-panel border border-cobalt/30 bg-paper px-4 py-3 shadow-float lg:top-4"
            >
              <p className="flex-1 text-[14px] text-ink">Your eligibility facts changed. Re-check to update your verdicts.</p>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={running}
                onClick={async () => {
                  await run();
                  toast.show("Verdicts updated");
                }}
              >
                {running ? <Spinner size={13} /> : <RefreshCw size={14} />}
                {running ? `Checking ${progress.done}/${progress.total}` : "Re-check now"}
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mt-8">
          <Completeness items={completeness(data, primary, mySkills.data?.length ?? 0)} />
        </div>

        <div className="mt-10 flex flex-col gap-10">
          <Section id="identity" title="About you" description="Citizenship and date of birth are read by published rules.">
            <IdentityForm profile={data} />
          </Section>
          <Section id="academic" title="Academic status" description="Your current degree level and whether you’re enrolled.">
            <AcademicForm profile={data} />
          </Section>
          <Section id="education" title="Primary education" description="GPA lives here, on the scale your institution uses.">
            {education.isPending ? <div className="skeleton h-48 w-full" /> : <EducationForm profile={data} primary={primary} />}
          </Section>
          <Section id="skills" title="Skills" description="Checked by rules that ask for specific skills. Changes save immediately.">
            <SkillsEditor />
          </Section>
          <Section
            id="test-scores"
            title="Test scores"
            description={
              <>
                Kept on your profile for reference. <span className="mt-1.5 block"><UsageTag used={false} /></span> No published rule evaluates test scores yet.
              </>
            }
          >
            <TestScores />
          </Section>
        </div>
      </Content>
    </Page>
  );
}
