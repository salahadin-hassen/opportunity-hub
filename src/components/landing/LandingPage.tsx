import React from 'react';
import { 
  ShieldCheck, 
  ArrowRight, 
  CheckCircle2, 
  XCircle, 
  AlertTriangle, 
  Sparkles, 
  FileCheck2, 
  ExternalLink, 
  Lock, 
  Clock, 
  Search,
  Check
} from 'lucide-react';

interface LandingPageProps {
  onStartOnboarding: () => void;
  onExploreCatalog: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onStartOnboarding,
  onExploreCatalog
}) => {
  return (
    <div className="min-h-screen bg-[#F9FAFB] text-ink">
      
      {/* Hero Section */}
      <section className="relative pt-12 pb-20 sm:pt-20 sm:pb-28 overflow-hidden">
        {/* Soft background ambient gradient */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[450px] bg-gradient-to-b from-accent-soft/80 via-accent-soft/20 to-transparent blur-3xl -z-10 pointer-events-none" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-accent-soft border border-indigo-200/60 text-accent text-xs font-semibold mb-6 shadow-xs animate-in fade-in slide-in-from-top-2 duration-300">
            <ShieldCheck className="w-4 h-4 text-accent" />
            <span>Deterministic Matching · No Vague Clickbait</span>
          </div>

          {/* Above-the-fold Headline */}
          <h1 className="text-3xl sm:text-5xl lg:text-6xl font-extrabold text-ink tracking-tight max-w-4xl mx-auto leading-[1.12]">
            Know <span className="text-accent underline decoration-accent/30 underline-offset-8">exactly</span> why you qualify. <br className="hidden sm:inline" />
            Before you spend 40 hours applying.
          </h1>

          {/* Pitch Subhead */}
          <p className="mt-6 text-base sm:text-xl text-grayText-600 max-w-2xl mx-auto font-normal leading-relaxed">
            Every match provides a verified row-by-row criteria breakdown with official sponsor bylaws and last-verified audit dates — never a vague “you might qualify.”
          </p>

          {/* Primary & Secondary CTAs */}
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3.5">
            <button
              onClick={onStartOnboarding}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white text-base font-semibold px-8 py-3.5 rounded-xl shadow-card hover:shadow-elevated transition-all group"
            >
              <span>Evaluate My Profile Free</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </button>

            <button
              onClick={onExploreCatalog}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-white hover:bg-gray-50 text-ink border border-gray-200 text-base font-medium px-6 py-3.5 rounded-xl shadow-subtle transition-all"
            >
              <span>Explore Opportunities</span>
            </button>
          </div>

          {/* Trust points */}
          <div className="mt-6 flex flex-wrap items-center justify-center gap-6 text-xs text-grayText-600 font-medium">
            <div className="flex items-center gap-1.5">
              <Check className="w-3.5 h-3.5 text-emerald-600 stroke-[3]" />
              <span>Zero manual GPA math</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Check className="w-3.5 h-3.5 text-emerald-600 stroke-[3]" />
              <span>Nuanced near-miss detection</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Check className="w-3.5 h-3.5 text-emerald-600 stroke-[3]" />
              <span>Official sponsor audit dates</span>
            </div>
          </div>

          {/* Hero Interactive Preview Mockup: The Row-by-Row Table */}
          <div className="mt-14 max-w-4xl mx-auto bg-white rounded-3xl border border-gray-200 shadow-elevated overflow-hidden text-left">
            <div className="p-4 sm:p-5 border-b border-gray-100 bg-surface-50/70 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex space-x-1.5">
                  <div className="w-3 h-3 rounded-full bg-rose-400" />
                  <div className="w-3 h-3 rounded-full bg-amber-400" />
                  <div className="w-3 h-3 rounded-full bg-emerald-400" />
                </div>
                <span className="text-xs font-mono text-grayText-600">
                  Opportunity Hub · Live Breakdown Preview
                </span>
              </div>
              <span className="text-[11px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-bold">
                ✓ 5 of 5 Met
              </span>
            </div>

            <div className="p-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                <div>
                  <h3 className="text-lg font-bold text-ink">Chevening Scholarship 2027</h3>
                  <p className="text-xs text-grayText-600">UK Gov't · Master's Degree · United Kingdom · Fully funded</p>
                </div>
                <span className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-bold inline-flex items-center gap-1.5 self-start sm:self-auto">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Eligible</span>
                </span>
              </div>

              {/* Sample Table Rows */}
              <div className="border border-gray-100 rounded-xl overflow-hidden divide-y divide-gray-100 text-xs font-mono">
                <div className="p-3 bg-surface-50 flex items-center justify-between text-grayText-600 font-bold text-[10px] uppercase">
                  <span>Requirement</span>
                  <span>Required Value</span>
                  <span>Alex's Profile</span>
                  <span>Status</span>
                </div>
                <div className="p-3 flex items-center justify-between hover:bg-surface-50/50">
                  <span className="font-sans font-semibold text-ink">Minimum GPA</span>
                  <span className="text-grayText-600">≥ 3.30 / 4.00</span>
                  <span className="text-emerald-700 font-bold">3.82 / 4.00</span>
                  <span className="text-emerald-700 font-sans font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Met
                  </span>
                </div>
                <div className="p-3 flex items-center justify-between hover:bg-surface-50/50">
                  <span className="font-sans font-semibold text-ink">English Language</span>
                  <span className="text-grayText-600">IELTS ≥ 6.5</span>
                  <span className="text-emerald-700 font-bold">IELTS 7.5</span>
                  <span className="text-emerald-700 font-sans font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Met
                  </span>
                </div>
                <div className="p-3 flex items-center justify-between hover:bg-surface-50/50">
                  <span className="font-sans font-semibold text-ink">Citizenship</span>
                  <span className="text-grayText-600">Chevening Country</span>
                  <span className="text-emerald-700 font-bold">Ethiopia (Citizen)</span>
                  <span className="text-emerald-700 font-sans font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Met
                  </span>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between text-[11px] text-grayText-600">
                <span className="flex items-center gap-1">
                  <ExternalLink className="w-3 h-3 text-accent" />
                  Official source: gov.uk/chevening
                </span>
                <span>Last verified 20 Sep 2026</span>
              </div>
            </div>
          </div>

        </div>
      </section>

      {/* Differentiator Section */}
      <section className="py-16 bg-white border-t border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">
              Why traditional scholarship sites waste your time
            </h2>
            <p className="mt-3 text-grayText-600 text-sm sm:text-base">
              Listing portals index thousands of scholarships by broad tags like "Engineering" or "International." Then you discover buried in PDF §4.2 that your country or graduation year isn't eligible.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="p-6 rounded-2xl bg-surface-50 border border-gray-200">
              <div className="w-10 h-10 rounded-xl bg-accent-soft text-accent flex items-center justify-center font-bold mb-4">
                1
              </div>
              <h3 className="text-base font-bold text-ink mb-2">Automated Ingestion</h3>
              <p className="text-xs sm:text-sm text-grayText-600 leading-relaxed">
                Drop your unofficial transcript and CV. Our system parses degree titles, GPA scales, courses, and internship timelines with 99.4% precision.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-surface-50 border border-gray-200">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-700 flex items-center justify-center font-bold mb-4">
                2
              </div>
              <h3 className="text-base font-bold text-ink mb-2">Row-by-Row Proof</h3>
              <p className="text-xs sm:text-sm text-grayText-600 leading-relaxed">
                Every requirement is explicitly laid out side-by-side with your profile and the sponsor’s mandatory threshold.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-surface-50 border border-gray-200">
              <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-700 flex items-center justify-center font-bold mb-4">
                3
              </div>
              <h3 className="text-base font-bold text-ink mb-2">Audited Citations</h3>
              <p className="text-xs sm:text-sm text-grayText-600 leading-relaxed">
                No stale databases or dead links. Every criterion links back to the official program statute with a "last verified" timestamp.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Call to Action Footer Banner */}
      <section className="py-16 bg-ink text-white">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight mb-4">
            Find out what you're actually eligible for today.
          </h2>
          <p className="text-gray-400 text-sm sm:text-base mb-8 max-w-xl mx-auto">
            Try the demo with Alex Mengistu’s profile or upload your own credentials to see verified matches.
          </p>
          <button
            onClick={onStartOnboarding}
            className="inline-flex items-center gap-2 bg-accent hover:bg-accent-light text-white font-semibold text-sm sm:text-base px-8 py-3.5 rounded-xl shadow-lg transition-all"
          >
            <span>Start Free Evaluation</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </section>

    </div>
  );
};
