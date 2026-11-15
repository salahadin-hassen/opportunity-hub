import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { OutcomeMark, VerdictBadge } from "../ui/Verdict";

/*
 * The engine, told in five steps on one real rule set: the GitHub Student
 * Developer Pack's two published rules (quotes from docs.github.com, as seeded).
 * The profile is an example. Outcomes follow the engine exactly: a missing
 * date of birth is "missing", not "failed"; once added, both rules are met and
 * the verdict is Eligible, which is still not GitHub's own decision.
 */

type Step = { title: string; body: string };

const STEPS: Step[] = [
  { title: "Start with you", body: "A short profile holds the facts published rules actually read: citizenship, degree level, enrolment, date of birth, GPA and skills." },
  { title: "Read the rules", body: "Each requirement is stored as a structured rule next to the exact sentence it came from on the official page." },
  { title: "Check one rule at a time", body: "The engine compares what’s required with what your profile holds. A fact you haven’t given is marked missing, never failed." },
  { title: "Get a verdict", body: "Rule outcomes roll up into one of four verdicts in a fixed order, so the same profile always gets the same answer." },
  { title: "Fill the gap, see it change", body: "Add the missing fact and only the affected opportunities are checked again. The evidence shows exactly what moved." },
];

const QUOTE_ENROLLED = "Are enrolled in a degree- or diploma-granting program, such as a high school, college, university, or homeschool.";
const QUOTE_AGE = "Are at least 13 years old.";

function Fact({ label, value, missing, fresh }: { label: string; value: string; missing?: boolean; fresh?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule py-2.5 last:border-b-0">
      <dt className="text-[14px] text-ink-soft">{label}</dt>
      <dd className={`num text-[13px] ${missing ? "text-potential-ink" : fresh ? "rounded bg-lime px-1.5 text-night" : "text-ink"}`}>{value}</dd>
    </div>
  );
}

function Rule({ n, label, outcome, quote }: { n: number; label: string; outcome: "met" | "unknown" | "pending"; quote?: boolean }) {
  return (
    <li className="flex gap-3 border-b border-rule py-3 last:border-b-0">
      <OutcomeMark outcome={outcome} size={20} />
      <div className="min-w-0">
        <p className="text-[14.5px] font-medium text-ink">
          {label}
          <sup className="num ml-0.5 text-[10px] text-cobalt-deep">[{n}]</sup>
        </p>
        {quote && <p className="mt-1 text-[13px] italic text-muted">“{n === 1 ? QUOTE_ENROLLED : QUOTE_AGE}”</p>}
      </div>
    </li>
  );
}

function Specimen({ step }: { step: number }) {
  const filled = step >= 4;
  const evaluated = step >= 2;
  let content: ReactNode;
  if (step === 0) {
    content = (
      <dl>
        <Fact label="Citizenship" value="Ethiopia" />
        <Fact label="Degree level" value="Bachelor’s" />
        <Fact label="Currently enrolled" value="Yes" />
        <Fact label="Date of birth" value="not given" missing />
      </dl>
    );
  } else {
    content = (
      <>
        <ul>
          <Rule n={1} label="Enrolled in a degree or diploma program" outcome={evaluated ? "met" : "pending"} quote={step === 1} />
          <Rule n={2} label="At least 13 years old" outcome={filled ? "met" : evaluated ? "unknown" : "pending"} quote={step === 1} />
        </ul>
        {step === 2 && (
          <dl className="mt-3 grid grid-cols-2 gap-3 rounded-[10px] bg-potential-wash/70 p-3 text-[13px]">
            <div>
              <dt className="text-muted">Required</dt>
              <dd className="num text-ink">born on or before 30 Oct 2013</dd>
            </div>
            <div>
              <dt className="text-muted">Your profile</dt>
              <dd className="num text-potential-ink">not given</dd>
            </div>
          </dl>
        )}
        {step === 4 && (
          <dl className="mt-3 grid grid-cols-2 gap-3 rounded-[10px] bg-eligible-wash p-3 text-[13px]">
            <div>
              <dt className="text-muted">Date of birth added</dt>
              <dd className="num text-ink">18 Apr 2003</dd>
            </div>
            <div>
              <dt className="text-muted">Rule 2</dt>
              <dd className="text-eligible-ink">was missing, now met</dd>
            </div>
          </dl>
        )}
      </>
    );
  }
  return (
    <div className="overflow-hidden rounded-panel border border-rule bg-paper shadow-float">
      <div className="flex items-center justify-between gap-4 border-b border-rule px-5 py-4">
        <div className="min-w-0">
          <p className="kicker">{step === 0 ? "Example profile" : "GitHub Education"}</p>
          <p className="heading mt-1 truncate text-[19px] text-ink">{step === 0 ? "Mekdes, bachelor’s student" : "GitHub Student Developer Pack"}</p>
        </div>
        <AnimatePresence mode="wait">
          {step >= 3 && (
            <motion.span key={filled ? "e" : "p"} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.3 }}>
              <VerdictBadge status={filled ? "eligible" : "potential_match"} size="md" />
            </motion.span>
          )}
        </AnimatePresence>
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
          className="px-5 py-3"
        >
          {content}
        </motion.div>
      </AnimatePresence>
      <div className="border-t border-rule bg-cream/60 px-5 py-3 text-[12.5px] text-muted">
        {step >= 4
          ? "Eligible means every published rule is met. GitHub still reviews the application."
          : "Rules [1] and [2] quoted from GitHub’s documentation. Example profile."}
      </div>
    </div>
  );
}

export function EngineStory() {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.step));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((node) => node && observer.observe(node));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-20">
      <ol className="flex flex-col">
        {STEPS.map((step, index) => (
          <li
            key={step.title}
            ref={(node) => {
              refs.current[index] = node;
            }}
            data-step={index}
            className="flex flex-col justify-center border-t border-rule py-10 lg:min-h-[34vh]"
          >
            <div className="flex items-baseline gap-4">
              <span className={`num text-[13px] transition-colors duration-300 ${active === index ? "text-persimmon-deep" : "text-faint"}`}>0{index + 1}</span>
              <h3 className={`heading text-[30px] transition-colors duration-300 sm:text-[38px] ${active === index ? "text-ink" : "text-ink/50"}`}>{step.title}</h3>
            </div>
            <p className={`mt-3 max-w-[46ch] pl-9 text-[16px] leading-relaxed transition-colors duration-300 ${active === index ? "text-ink-soft" : "text-muted"}`}>{step.body}</p>
            <div className="mt-8 lg:hidden">
              <Specimen step={index} />
            </div>
          </li>
        ))}
      </ol>
      <div className="hidden lg:block">
        <div className="sticky top-[calc(50vh-200px)]">
          <Specimen step={active} />
        </div>
      </div>
    </div>
  );
}
