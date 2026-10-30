import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, Check } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import { ApiError, api, unwrap } from "../api/client";
import { keys, useCreateProfile, useProfile, useSaveEducation, useSkillCatalog } from "../api/queries";
import type { DegreeLevel } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Page } from "../components/layout/Page";
import { CountryMulti, DegreeSelect, Field, SkillPicker, Toggle } from "../components/ui/FormBits";
import { Logo } from "../components/ui/Logo";
import { ErrorState, Spinner } from "../components/ui/States";
import { useEligibility } from "../features/eligibility";
import { countryOptions } from "../lib/countries";
import { Plate } from "../components/ui/Plate";
import type { PhotoKey } from "../lib/photos";
import { ThemeToggle } from "../components/ui/ThemeToggle";

const STEPS = ["About you", "Education", "Skills"] as const;

const STEP_PHOTO: PhotoKey[] = ["campusPath", "readingRoom", "radioTelescope"];

/** The reason each step exists, in the user's terms. */
const STEP_WHY = [
  "Many programs are open only to certain citizenships or age ranges. With these, the engine can tell you about those rules instead of leaving them undecided.",
  "Degree level, enrolment and GPA are the facts published rules read most often. GPA is kept on its own scale, so it’s only compared with thresholds on that scale.",
  "Some programs ask for specific skills. Choose the ones you’d be comfortable being assessed on; they’re matched only against rules that name them.",
];

type Draft = {
  full_name: string;
  email: string;
  date_of_birth: string;
  citizenships: string[];
  country_of_residence: string;
  degree_level: DegreeLevel | "";
  is_currently_enrolled: boolean;
  institution_name: string;
  field_of_study: string;
  gpa: string;
  gpa_scale: string;
  skills: Set<string>;
};

type Phase = "form" | "saving" | "checking";

function Stepper({ step }: { step: number }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Progress">
      {STEPS.map((label, index) => {
        const done = index < step;
        const current = index === step;
        return (
          <li key={label} className="flex items-center gap-2" aria-current={current ? "step" : undefined}>
            <span
              className={`inline-flex size-6 items-center justify-center rounded-full text-[12px] font-medium transition-colors duration-200 ${
                done ? "bg-ink text-on-ink" : current ? "bg-cobalt text-white" : "bg-paper text-muted ring-1 ring-inset ring-rule-strong"
              }`}
            >
              {done ? <Check size={13} strokeWidth={3} /> : index + 1}
            </span>
            <span className={`hidden text-[13px] sm:inline ${current ? "font-medium text-ink" : "text-muted"}`}>{label}</span>
            {index < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-rule-strong sm:w-10" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}

export function Onboarding() {
  const { email } = useAuth();
  const profile = useProfile();
  const catalog = useSkillCatalog();
  const createProfile = useCreateProfile();
  const saveEducation = useSaveEducation();
  const client = useQueryClient();
  const { run, progress } = useEligibility();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [phase, setPhase] = useState<Phase>("form");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const created = useRef<{ profile: boolean; education: boolean }>({ profile: false, education: false });
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [draft, setDraft] = useState<Draft>({
    full_name: "",
    email: email ?? "",
    date_of_birth: "",
    citizenships: [],
    country_of_residence: "",
    degree_level: "",
    is_currently_enrolled: true,
    institution_name: "",
    field_of_study: "",
    gpa: "",
    gpa_scale: "4",
    skills: new Set(),
  });

  useEffect(() => headingRef.current?.focus(), [step]);

  // Someone who already has a profile has nothing to onboard.
  if (profile.data && phase === "form" && !created.current.profile) return <Navigate to="/discover" replace />;

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((old) => ({ ...old, [key]: value }));

  function validate(index: number): boolean {
    const next: Record<string, string> = {};
    if (index === 0) {
      if (!draft.full_name.trim()) next.full_name = "Enter your name.";
      if (!/^\S+@\S+\.\S+$/.test(draft.email)) next.email = "Enter a valid email address.";
      if (draft.date_of_birth && draft.date_of_birth > new Date().toISOString().slice(0, 10)) next.date_of_birth = "Date of birth can’t be in the future.";
    }
    if (index === 1) {
      if (!draft.degree_level) next.degree_level = "Choose your current degree level.";
      if (!draft.institution_name.trim()) next.institution_name = "Enter your institution.";
      if (!draft.field_of_study.trim()) next.field_of_study = "Enter your field of study.";
      if (draft.gpa) {
        const gpa = Number(draft.gpa);
        if (!Number.isFinite(gpa) || gpa < 0 || gpa > Number(draft.gpa_scale)) next.gpa = `Enter a GPA between 0 and ${draft.gpa_scale}.`;
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function finish() {
    setFormError(null);
    setPhase("saving");
    try {
      if (!created.current.profile) {
        await createProfile.mutateAsync({
          full_name: draft.full_name.trim(),
          email: draft.email.trim(),
          date_of_birth: draft.date_of_birth || null,
          citizenships: draft.citizenships,
          country_of_residence: draft.country_of_residence || null,
          degree_level: draft.degree_level as DegreeLevel,
          is_currently_enrolled: draft.is_currently_enrolled,
        });
        created.current.profile = true;
      }
      if (!created.current.education) {
        await saveEducation.mutateAsync({
          body: {
            institution_name: draft.institution_name.trim(),
            degree_level: draft.degree_level as DegreeLevel,
            field_of_study: draft.field_of_study.trim(),
            is_current: draft.is_currently_enrolled,
            is_primary: true,
            gpa: draft.gpa ? Number(draft.gpa) : null,
            gpa_scale: draft.gpa ? Number(draft.gpa_scale) : null,
          },
        });
        created.current.education = true;
      }
      for (const skillId of draft.skills) {
        try {
          await unwrap(api.POST("/me/profile/skills", { body: { skill_id: skillId } }));
        } catch (error) {
          // Already attached on a retried submit: that is the state we want.
          if (!(error instanceof ApiError && error.status === 409)) throw error;
        }
      }
      await client.invalidateQueries({ queryKey: keys.mySkills });
      setPhase("checking");
      await run();
      navigate("/eligibility", { replace: true });
    } catch (error) {
      setPhase("form");
      if (error instanceof ApiError && Object.keys(error.fields).length) {
        setErrors(error.fields);
        setStep(error.fields.gpa || error.fields.institution_name ? 1 : 0);
      }
      setFormError(error instanceof ApiError ? error.message : "Something went wrong while saving. Try again.");
    }
  }

  function next(event: FormEvent) {
    event.preventDefault();
    if (!validate(step)) return;
    if (step < STEPS.length - 1) setStep(step + 1);
    else void finish();
  }

  if (phase !== "form") {
    const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
    return (
      <Page title="Checking eligibility">
        <div className="flex min-h-dvh items-center bg-ivory px-5">
          <div className="mx-auto w-full max-w-[760px]" role="status" aria-live="polite">
            <p className="kicker">{phase === "saving" ? "Step 1 of 2" : "Step 2 of 2"}</p>
            <p className="display mt-4 text-[48px] text-ink sm:text-[72px]">
              {phase === "saving" ? "Saving your profile." : "Checking every published rule."}
            </p>
            <div className="mt-10 flex items-end justify-between gap-6 border-b border-ink pb-4">
              <p className="max-w-[40ch] text-[16px] text-ink-soft">
                {phase === "saving" ? "Creating your profile, education and skills." : "Each opportunity is evaluated against your profile by the engine, four at a time."}
              </p>
              {phase === "checking" && (
                <p className="display shrink-0 text-[56px] text-ink">
                  {progress.done}
                  <span className="text-faint">/{progress.total}</span>
                </p>
              )}
            </div>
            <div className="mt-6 h-2 overflow-hidden rounded-full bg-cream">
              <motion.div
                className="h-full rounded-full bg-cobalt"
                animate={{ width: phase === "saving" ? "6%" : `${Math.max(6, percent)}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </div>
        </div>
      </Page>
    );
  }

  const skills = catalog.data ?? [];

  return (
    <Page title="Set up your profile">
      <div className="min-h-dvh bg-ivory">
        <header className="mx-auto flex h-16 max-w-[1240px] items-center justify-between px-5 sm:px-8">
          <Logo />
          <div className="flex items-center gap-3">
            <Stepper step={step} />
            <ThemeToggle />
          </div>
        </header>
        <div className="mx-auto grid max-w-[1240px] grid-cols-1 gap-12 px-5 pb-16 pt-6 sm:px-8 sm:pt-12 lg:grid-cols-12">
        <main id="main" className="lg:col-span-7">
          <form onSubmit={next} noValidate>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={step}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              >
                {step === 0 && (
                  <>
                    <h1 ref={headingRef} tabIndex={-1} className="display text-[44px] text-ink outline-none sm:text-[56px]">
                      Tell us about yourself
                    </h1>
                    <p className="mt-2 max-w-[56ch] text-[14.5px] text-muted">
                      Fields marked <span className="font-medium text-cobalt-deep">Used in eligibility</span> are read by published rules. Anything else is stored for you but never changes a verdict.
                    </p>
                    <div className="sheet mt-8 flex flex-col gap-5 p-5 sm:p-6">
                      <Field id="full_name" label="Full name" error={errors.full_name}>
                        <input id="full_name" className="input" autoComplete="name" value={draft.full_name} onChange={(event) => set("full_name", event.target.value)} aria-invalid={Boolean(errors.full_name)} />
                      </Field>
                      <Field id="email" label="Contact email" error={errors.email}>
                        <input id="email" type="email" className="input" autoComplete="email" value={draft.email} onChange={(event) => set("email", event.target.value)} aria-invalid={Boolean(errors.email)} />
                      </Field>
                      <Field
                        id="citizenships"
                        label="Citizenship"
                        used
                        why="Many programs are limited to, or exclude, certain citizenships. Add every citizenship you hold."
                      >
                        <CountryMulti id="citizenships" values={draft.citizenships} onChange={(values) => set("citizenships", values)} />
                      </Field>
                      <Field
                        id="date_of_birth"
                        label="Date of birth"
                        used
                        optional
                        why="Age limits are checked against it. Leave it empty and age rules stay undecided."
                        error={errors.date_of_birth}
                      >
                        <input
                          id="date_of_birth"
                          type="date"
                          className="input"
                          max={new Date().toISOString().slice(0, 10)}
                          value={draft.date_of_birth}
                          onChange={(event) => set("date_of_birth", event.target.value)}
                          aria-invalid={Boolean(errors.date_of_birth)}
                        />
                      </Field>
                      <Field id="residence" label="Country of residence" used={false} optional why="Kept for your profile. No rule reads it yet.">
                        <select id="residence" className="input" value={draft.country_of_residence} onChange={(event) => set("country_of_residence", event.target.value)}>
                          <option value="">Not set</option>
                          <OptionsForCountries />
                        </select>
                      </Field>
                    </div>
                  </>
                )}

                {step === 1 && (
                  <>
                    <h1 ref={headingRef} tabIndex={-1} className="display text-[44px] text-ink outline-none sm:text-[56px]">
                      Your education
                    </h1>
                    <p className="mt-2 max-w-[56ch] text-[14.5px] text-muted">This becomes your primary education record. Degree level, enrolment and GPA are the facts rules check most often.</p>
                    <div className="sheet mt-8 flex flex-col gap-5 p-5 sm:p-6">
                      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                        <Field id="degree_level" label="Current degree level" used error={errors.degree_level} why="Matched against degree requirements.">
                          <DegreeSelect id="degree_level" value={draft.degree_level} onChange={(value) => set("degree_level", value)} />
                        </Field>
                        <Field id="enrolled" label="Enrolment" used why="Many programs require current enrolment.">
                          <div className="flex h-10 items-center">
                            <Toggle id="enrolled" checked={draft.is_currently_enrolled} onChange={(value) => set("is_currently_enrolled", value)} label="I’m currently enrolled" />
                          </div>
                        </Field>
                      </div>
                      <Field id="institution_name" label="Institution" used={false} error={errors.institution_name}>
                        <input id="institution_name" className="input" placeholder="Addis Ababa University" value={draft.institution_name} onChange={(event) => set("institution_name", event.target.value)} aria-invalid={Boolean(errors.institution_name)} />
                      </Field>
                      <Field id="field_of_study" label="Field of study" used={false} error={errors.field_of_study} why="Stored for your profile. Field-of-study rules are left for your review.">
                        <input id="field_of_study" className="input" placeholder="Aerospace Engineering" value={draft.field_of_study} onChange={(event) => set("field_of_study", event.target.value)} aria-invalid={Boolean(errors.field_of_study)} />
                      </Field>
                      <Field
                        id="gpa"
                        label="GPA"
                        used
                        optional
                        error={errors.gpa}
                        why="Compared only with thresholds published on the same scale. A different scale goes to your review instead of being converted."
                      >
                        <div className="flex gap-2">
                          <input id="gpa" type="number" inputMode="decimal" step="0.01" min={0} className="input num flex-1" placeholder="3.72" value={draft.gpa} onChange={(event) => set("gpa", event.target.value)} aria-invalid={Boolean(errors.gpa)} />
                          <label htmlFor="gpa_scale" className="sr-only">
                            GPA scale
                          </label>
                          <select id="gpa_scale" className="input w-28" value={draft.gpa_scale} onChange={(event) => set("gpa_scale", event.target.value)}>
                            <option value="4">of 4.0</option>
                            <option value="5">of 5.0</option>
                            <option value="10">of 10</option>
                            <option value="100">of 100</option>
                          </select>
                        </div>
                      </Field>
                    </div>
                  </>
                )}

                {step === 2 && (
                  <>
                    <h1 ref={headingRef} tabIndex={-1} className="display text-[44px] text-ink outline-none sm:text-[56px]">
                      Your skills
                    </h1>
                    <p className="mt-2 max-w-[56ch] text-[14.5px] text-muted">
                      Pick the skills you’d be comfortable being assessed on. Rules that ask for specific skills are checked against this list.
                    </p>
                    <div className="sheet mt-8 p-5 sm:p-6">
                      <div className="mb-3 flex items-center gap-2">
                        <span className="text-[13px] font-medium text-ink">Skills</span>
                        <span className="inline-flex items-center gap-1 rounded-full bg-cobalt-wash px-1.5 py-px text-[11px] font-medium text-cobalt-deep">
                          <Check size={10} strokeWidth={3} />
                          Used in eligibility
                        </span>
                        <span className="ml-auto text-[12.5px] text-muted">{draft.skills.size} selected</span>
                      </div>
                      {catalog.isPending ? (
                        <div className="flex flex-wrap gap-1.5">
                          {Array.from({ length: 12 }, (_, index) => (
                            <div key={index} className="skeleton h-8 w-24" />
                          ))}
                        </div>
                      ) : catalog.isError ? (
                        <ErrorState message="The skill list couldn’t load. You can add skills later from your profile." />
                      ) : (
                        <SkillPicker
                          catalog={skills}
                          selected={draft.skills}
                          onToggle={(skill) => {
                            const nextSet = new Set(draft.skills);
                            if (nextSet.has(skill.id)) nextSet.delete(skill.id);
                            else nextSet.add(skill.id);
                            set("skills", nextSet);
                          }}
                        />
                      )}
                    </div>
                    <p className="mt-4 text-[13px] text-muted">When you continue, your profile is saved and every published opportunity is checked against it.</p>
                  </>
                )}
              </motion.div>
            </AnimatePresence>

            {formError && <div className="mt-5"><ErrorState message={formError} /></div>}

            <div className="mt-8 flex items-center justify-between">
              {step > 0 ? (
                <button type="button" className="btn btn-ghost" onClick={() => setStep(step - 1)}>
                  <ArrowLeft size={15} />
                  Back
                </button>
              ) : (
                <span />
              )}
              <button type="submit" className="btn btn-primary btn-lg">
                {phase !== "form" && <Spinner size={15} />}
                {step < STEPS.length - 1 ? "Continue" : "Save and check my eligibility"}
              </button>
            </div>
          </form>
        </main>
        <aside className="hidden lg:col-span-4 lg:col-start-9 lg:block">
          <div className="sticky top-8">
            <Plate photo={STEP_PHOTO[step]!} number={`Pl. ${step + 1}`} ratio={4 / 5} sizes="30vw" />
            <div className="mt-8 border-t border-ink pt-5">
              <p className="heading text-[20px] text-ink">Why we ask</p>
              <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">{STEP_WHY[step]}</p>
            </div>
          </div>
        </aside>
        </div>
      </div>
    </Page>
  );
}

function OptionsForCountries() {
  return (
    <>
      {countryOptions().map((country) => (
        <option key={country.code} value={country.code}>
          {country.name}
        </option>
      ))}
    </>
  );
}

