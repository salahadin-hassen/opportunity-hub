import { Page } from "../components/layout/Page";
import { MarketingFooter, MarketingNav } from "../components/marketing/MarketingChrome";

const STORED: [string, string][] = [
  ["Your account", "Your email address and a one-way, salted hash of your password (Argon2id). We can’t read your password."],
  [
    "Facts eligibility rules read",
    "Citizenship, date of birth, degree level, whether you’re enrolled, your primary education’s GPA and its scale, and your skills. The engine compares these with each opportunity’s published rules.",
  ],
  [
    "Facts stored only for your profile",
    "Your name, contact email, country of residence, institution, field of study and any test scores you add. No published rule reads them, so they never change a verdict.",
  ],
  ["Your results", "Each eligibility check’s verdict, the rule-by-rule evidence and when it ran, so you can come back to it."],
];

export function Privacy() {
  return (
    <Page title="Privacy">
      <MarketingNav />
      <main id="main" className="mx-auto max-w-[820px] px-5 pb-10 pt-32 sm:px-8">
        <h1 className="display text-[52px] text-ink sm:text-[80px]">What we store, and why</h1>
        <p className="mt-6 max-w-[62ch] text-[17px] text-ink-soft">
          Opportunity Hub keeps the profile facts it needs to check eligibility rules, and nothing it doesn’t. This page describes the current
          service in plain terms. It isn’t a legal certification of any kind.
        </p>

        <dl className="mt-12 border-t border-ink">
          {STORED.map(([title, body]) => (
            <div key={title} className="grid grid-cols-1 gap-2 border-b border-rule py-6 sm:grid-cols-[220px_minmax(0,1fr)] sm:gap-8">
              <dt className="heading text-[19px] text-ink">{title}</dt>
              <dd className="text-[15.5px] leading-relaxed text-ink-soft">{body}</dd>
            </div>
          ))}
        </dl>

        <section className="mt-12 flex flex-col gap-5 text-[15.5px] leading-relaxed text-ink-soft">
          <h2 className="heading text-[26px] text-ink">What we don’t do</h2>
          <p>We never ask you to upload documents. We don’t share your profile with the organizations listed here, sell it, or use advertising or analytics trackers. Fonts and photographs are served from our own site.</p>
          <h2 className="heading mt-4 text-[26px] text-ink">In your browser</h2>
          <p>
            Your sign-in session (it expires after 30 minutes), your light or dark theme choice, and any conditions you tick as confirmed are kept in your
            browser’s local storage on this device only.
          </p>
          <h2 className="heading mt-4 text-[26px] text-ink">Good to know</h2>
          <p>
            Opportunity Hub is an early, hackathon-stage service. Profiles are stored in a PostgreSQL database run by our hosting provider. Deleting an
            account isn’t self-service yet, so please don’t enter anything you wouldn’t want stored. Example or approximate details are fine for
            exploring.
          </p>
          <p>A verdict compares your profile with published rules. It isn’t an admission, award or approval: the organization makes that decision.</p>
        </section>
      </main>
      <MarketingFooter />
    </Page>
  );
}
