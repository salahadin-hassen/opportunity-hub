import React, { useState } from 'react';
import { 
  ArrowLeft, 
  Share2, 
  Bookmark, 
  Check, 
  AlertTriangle, 
  X, 
  ExternalLink, 
  Calendar, 
  MapPin, 
  Clock, 
  Building2, 
  ShieldCheck, 
  CheckCircle2, 
  XCircle, 
  AlertCircle,
  Sparkles,
  Award,
  Globe,
  DollarSign,
  ChevronRight,
  Copy,
  CheckCheck
} from 'lucide-react';
import { Opportunity, StudentProfile } from '../../types/opportunity';
import { StatusBadge } from '../common/StatusBadge';
import { ExpiredState } from '../common/SystemStates';

interface OpportunityDetailProps {
  opportunity: Opportunity;
  student: StudentProfile;
  isSaved: boolean;
  onToggleSave: (id: string, e: React.MouseEvent) => void;
  onBack: () => void;
  onSelectAlternativeOpportunity: (id: string) => void;
  allOpportunities: Opportunity[];
}

export const OpportunityDetail: React.FC<OpportunityDetailProps> = ({
  opportunity,
  student,
  isSaved,
  onToggleSave,
  onBack,
  onSelectAlternativeOpportunity,
  allOpportunities
}) => {
  const [copiedShare, setCopiedShare] = useState(false);
  const evaluation = opportunity.evaluateEligibility(student);

  const handleShare = () => {
    navigator.clipboard?.writeText(window.location.href);
    setCopiedShare(true);
    setTimeout(() => setCopiedShare(false), 2000);
  };

  const isEligible = evaluation.status === 'eligible';
  const isPotential = evaluation.status === 'potential';
  const isNotEligible = evaluation.status === 'not-eligible';

  return (
    <div className="min-h-screen pb-20">
      
      {/* Top Breadcrumb Header Bar */}
      <div className="bg-white border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs sm:text-sm text-grayText-600">
            <button 
              onClick={onBack}
              className="hover:text-accent font-medium flex items-center gap-1 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Discover</span>
            </button>
            <ChevronRight className="w-3.5 h-3.5 text-grayText-400" />
            <span className="font-semibold text-ink truncate max-w-[200px] sm:max-w-md">
              {opportunity.name}
            </span>
          </div>

          {/* Quick Demo Switcher Between Nuanced Eligible and Not-Eligible Examples */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-mono text-grayText-400 hidden sm:inline">Compare:</span>
            <button
              onClick={() => onSelectAlternativeOpportunity('chevening-2027')}
              className={`px-2 py-1 rounded text-[11px] font-semibold border transition-all ${
                opportunity.id === 'chevening-2027' 
                  ? 'bg-emerald-600 text-white border-emerald-600 shadow-xs' 
                  : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
              }`}
            >
              Eligible (Chevening)
            </button>
            <button
              onClick={() => onSelectAlternativeOpportunity('mastercard-scholars-2027')}
              className={`px-2 py-1 rounded text-[11px] font-semibold border transition-all ${
                opportunity.id === 'mastercard-scholars-2027' 
                  ? 'bg-rose-600 text-white border-rose-600 shadow-xs' 
                  : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
              }`}
            >
              Near-Miss (Mastercard)
            </button>
            <button
              onClick={() => onSelectAlternativeOpportunity('daad-rise-2026')}
              className={`px-2 py-1 rounded text-[11px] font-semibold border transition-all ${
                opportunity.id === 'daad-rise-2026' 
                  ? 'bg-amber-600 text-white border-amber-600 shadow-xs' 
                  : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
              }`}
            >
              Potential (DAAD)
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        
        {/* Main Opportunity Header Block */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-8 mb-8">
          <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6">
            
            {/* Title & Metadata */}
            <div className="flex-1">
              <div className="flex items-center gap-2.5 mb-2.5 flex-wrap">
                <span className="px-3 py-1 rounded-full bg-accent-soft text-accent text-xs font-bold font-mono uppercase tracking-wider">
                  {opportunity.category}
                </span>
                <span className="px-3 py-1 rounded-full bg-surface-100 text-ink text-xs font-semibold font-mono">
                  {opportunity.funding}
                </span>
                {opportunity.isApproachingDeadline && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-orange-50 text-orange-800 border border-orange-200 text-xs font-bold font-mono">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Approaching Deadline</span>
                  </span>
                )}
              </div>

              <h1 className="text-2xl sm:text-4xl font-extrabold text-ink tracking-tight mb-2">
                {opportunity.name}
              </h1>

              {/* Subtitles: org · category; type · location · funding · duration */}
              <div className="space-y-1.5 text-xs sm:text-sm text-grayText-600 font-medium">
                <p className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-ink text-sm sm:text-base">{opportunity.organization}</span>
                  <span className="text-grayText-400">·</span>
                  <span className="text-gray-700">{opportunity.category}</span>
                </p>
                <p className="flex items-center gap-2 flex-wrap text-gray-600 font-mono text-xs">
                  <span>{opportunity.type}</span>
                  <span className="text-grayText-400">·</span>
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5 text-grayText-400" />
                    {opportunity.location}
                  </span>
                  <span className="text-grayText-400">·</span>
                  <span>{opportunity.funding}</span>
                  <span className="text-grayText-400">·</span>
                  <span>{opportunity.duration}</span>
                </p>
              </div>
            </div>

            {/* Action Buttons: Share, Bookmark, Official Apply */}
            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={handleShare}
                className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 text-ink text-xs sm:text-sm font-semibold transition-all shadow-xs"
              >
                {copiedShare ? (
                  <>
                    <CheckCheck className="w-4 h-4 text-emerald-600" />
                    <span className="text-emerald-700">Link Copied</span>
                  </>
                ) : (
                  <>
                    <Share2 className="w-4 h-4 text-grayText-600" />
                    <span>Share</span>
                  </>
                )}
              </button>

              <button
                onClick={(e) => onToggleSave(opportunity.id, e)}
                className={`inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border text-xs sm:text-sm font-semibold transition-all shadow-xs ${
                  isSaved
                    ? 'bg-accent-soft text-accent border-accent/40 hover:bg-indigo-100'
                    : 'border-gray-200 text-ink hover:bg-gray-50'
                }`}
              >
                <Bookmark className={`w-4 h-4 ${isSaved ? 'fill-accent' : ''}`} />
                <span>{isSaved ? 'Saved' : 'Save'}</span>
              </button>

              <a
                href={opportunity.source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-xs sm:text-sm font-semibold px-5 py-2.5 rounded-xl shadow-sm hover:shadow transition-all"
              >
                <span>Official Portal</span>
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>

          </div>
        </div>

        {/* Expired Program Banner (If applicable e.g. Rhodes) */}
        {opportunity.isExpired && (
          <div className="mb-8">
            <ExpiredState 
              programName={opportunity.name} 
              nextCycleDate={opportunity.nextCycleDate || 'June 2027'} 
            />
          </div>
        )}

        {/* STATUS BANNER (As specified) */}
        <div className="mb-8">
          {isEligible && (
            <div className="p-5 rounded-2xl bg-emerald-50 border border-emerald-200/90 shadow-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start sm:items-center gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center shrink-0 shadow-xs">
                  <CheckCircle2 className="w-6 h-6 stroke-[2.5]" />
                </div>
                <div>
                  <h3 className="text-base sm:text-lg font-bold text-emerald-950">
                    Eligible — all requirements satisfied
                  </h3>
                  <p className="text-xs sm:text-sm text-emerald-800">
                    Your academic record at {student.education.university} satisfies 100% of the verified prerequisite criteria for this program.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-900 font-mono text-xs font-bold">
                  {evaluation.criteriaChecks.length}/{evaluation.criteriaChecks.length} Criteria Met
                </span>
              </div>
            </div>
          )}

          {isNotEligible && (
            <div className="p-5 rounded-2xl bg-rose-50 border border-rose-200/90 shadow-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start sm:items-center gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-rose-600 text-white flex items-center justify-center shrink-0 shadow-xs">
                  <XCircle className="w-6 h-6 stroke-[2.5]" />
                </div>
                <div>
                  <h3 className="text-base sm:text-lg font-bold text-rose-950">
                    Not currently eligible — {evaluation.unmetCount} requirement{evaluation.unmetCount > 1 ? 's' : ''} not met
                  </h3>
                  <p className="text-xs sm:text-sm text-rose-800">
                    <strong>Nuanced Near-Miss:</strong> You satisfy {evaluation.criteriaChecks.length - evaluation.unmetCount} out of {evaluation.criteriaChecks.length} criteria. Review the specific unmet row below to see the exact cutoff gap.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="px-3 py-1 rounded-full bg-rose-100 text-rose-900 font-mono text-xs font-bold">
                  {evaluation.unmetCount} Unmet Criterion
                </span>
              </div>
            </div>
          )}

          {isPotential && (
            <div className="p-5 rounded-2xl bg-amber-50 border border-amber-200/90 shadow-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start sm:items-center gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-amber-600 text-white flex items-center justify-center shrink-0 shadow-xs">
                  <AlertTriangle className="w-6 h-6 stroke-[2.5]" />
                </div>
                <div>
                  <h3 className="text-base sm:text-lg font-bold text-amber-950">
                    Potential match — {evaluation.uncertainCount} criterion pending confirmation
                  </h3>
                  <p className="text-xs sm:text-sm text-amber-800">
                    You meet all verified academic prerequisites, but one qualitative assessment requires host institution review or score submission.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="px-3 py-1 rounded-full bg-amber-100 text-amber-900 font-mono text-xs font-bold">
                  Review Pending
                </span>
              </div>
            </div>
          )}
        </div>

        {/* "WHY YOU MATCH" TABLE — THE CENTRAL DIFFERENTIATOR */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card overflow-hidden mb-8">
          
          {/* Table Header Callout */}
          <div className="p-5 sm:p-6 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface-50/50">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <ShieldCheck className="w-5 h-5 text-accent" />
                <h2 className="text-lg sm:text-xl font-bold text-ink">Why you match</h2>
              </div>
              <p className="text-xs sm:text-sm text-grayText-600">
                Row-by-row verified rule evaluation directly against Alex Mengistu’s academic credentials.
              </p>
            </div>
            <div className="inline-flex items-center gap-2 text-xs font-mono text-grayText-600">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              <span>Verified Rule Engine</span>
            </div>
          </div>

          {/* Responsive Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-50 border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-grayText-600 font-mono">
                  <th className="py-3.5 px-4 sm:px-6 w-[28%]">Requirement</th>
                  <th className="py-3.5 px-4 sm:px-6 w-[30%]">Required</th>
                  <th className="py-3.5 px-4 sm:px-6 w-[28%]">Your Profile</th>
                  <th className="py-3.5 px-4 sm:px-6 text-center w-[14%]">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 text-xs sm:text-sm">
                {evaluation.criteriaChecks.map((criterion) => {
                  return (
                    <tr 
                      key={criterion.id}
                      className={`hover:bg-surface-50/70 transition-colors ${
                        criterion.status === 'unmet' ? 'bg-rose-50/20' : ''
                      }`}
                    >
                      {/* Column 1: Requirement Name + Citation section */}
                      <td className="py-4 px-4 sm:px-6 align-top">
                        <div className="font-semibold text-ink mb-1">
                          {criterion.label}
                        </div>
                        {criterion.sourceSection && (
                          <span className="text-[10px] font-mono text-grayText-400 block">
                            Ref: {criterion.sourceSection}
                          </span>
                        )}
                        {criterion.note && (
                          <p className={`text-xs mt-1 font-medium ${
                            criterion.status === 'met' 
                              ? 'text-emerald-700' 
                              : criterion.status === 'unmet' 
                              ? 'text-rose-700' 
                              : 'text-amber-700'
                          }`}>
                            {criterion.note}
                          </p>
                        )}
                      </td>

                      {/* Column 2: Required */}
                      <td className="py-4 px-4 sm:px-6 align-top font-mono text-xs text-gray-700">
                        <span className="inline-block bg-surface-100 px-2.5 py-1 rounded-md border border-gray-200/80">
                          {criterion.required}
                        </span>
                      </td>

                      {/* Column 3: Your profile */}
                      <td className="py-4 px-4 sm:px-6 align-top font-mono text-xs">
                        <span className={`inline-block px-2.5 py-1 rounded-md border font-semibold ${
                          criterion.status === 'met'
                            ? 'bg-emerald-50 text-emerald-900 border-emerald-200'
                            : criterion.status === 'unmet'
                            ? 'bg-rose-50 text-rose-900 border-rose-200'
                            : 'bg-amber-50 text-amber-900 border-amber-200'
                        }`}>
                          {criterion.studentValue}
                        </span>
                      </td>

                      {/* Column 4: Status (✓/✕/⚠) */}
                      <td className="py-4 px-4 sm:px-6 align-top text-center">
                        {criterion.status === 'met' && (
                          <span className="inline-flex items-center justify-center gap-1 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 font-bold text-xs">
                            <Check className="w-3.5 h-3.5 text-emerald-600 stroke-[3]" />
                            <span>Met</span>
                          </span>
                        )}
                        {criterion.status === 'uncertain' && (
                          <span className="inline-flex items-center justify-center gap-1 px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 font-bold text-xs">
                            <AlertTriangle className="w-3.5 h-3.5 text-amber-600 stroke-[2.5]" />
                            <span>Uncertain</span>
                          </span>
                        )}
                        {criterion.status === 'unmet' && (
                          <span className="inline-flex items-center justify-center gap-1 px-2.5 py-1 rounded-full bg-rose-100 text-rose-800 font-bold text-xs">
                            <X className="w-3.5 h-3.5 text-rose-600 stroke-[3]" />
                            <span>Unmet</span>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Source Line with Official Link + "Last verified [date]" (As specified) */}
          <div className="p-4 sm:p-5 bg-surface-50 border-t border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 text-grayText-600">
              <Globe className="w-4 h-4 text-accent shrink-0" />
              <span>
                Source: <a href={opportunity.source.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-accent hover:underline">{opportunity.source.name}</a>
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-grayText-600 font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span>Last verified <strong className="text-ink">{opportunity.source.lastVerified}</strong> by Opportunity Hub Academic Audit</span>
            </div>
          </div>

        </div>

        {/* Opportunity Summary Grid: About / Covers / Fields / Deadline */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Left Column (2 Cols wide): About & Covers */}
          <div className="lg:col-span-2 space-y-8">
            
            {/* About */}
            <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
              <h3 className="text-base font-bold text-ink mb-3">About the Program</h3>
              <p className="text-sm leading-relaxed text-grayText-600">
                {opportunity.about}
              </p>
            </div>

            {/* What is covered (Funding breakdown) */}
            <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
              <h3 className="text-base font-bold text-ink mb-4 flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-emerald-600" />
                <span>Financial Coverage & Benefits</span>
              </h3>
              <div className="space-y-2.5">
                {opportunity.covers.map((benefit, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-surface-50 border border-gray-100 text-xs sm:text-sm">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <span className="font-medium text-ink">{benefit}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* Right Column: Fields, Deadlines & Next Steps */}
          <div className="space-y-6">
            
            {/* Deadline Card */}
            <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6">
              <div className="flex items-center gap-2 mb-3">
                <Calendar className="w-4 h-4 text-accent" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-ink font-mono">
                  Application Deadline
                </h4>
              </div>

              <p className="text-2xl font-extrabold text-ink font-mono mb-1">
                {opportunity.deadlineFormatted}
              </p>
              <p className="text-xs text-grayText-600 font-mono mb-4">
                23:59 UTC · Sponsoring Institution Portal
              </p>

              <a
                href={opportunity.source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white text-xs sm:text-sm font-semibold py-3 rounded-xl shadow-sm transition-all"
              >
                <span>Begin Official Application</span>
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>

            {/* Eligible Fields */}
            <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6">
              <h4 className="text-xs font-bold uppercase tracking-wider text-ink font-mono mb-3">
                Eligible Disciplines
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {opportunity.fields.map((field, i) => (
                  <span 
                    key={i}
                    className="px-2.5 py-1 rounded-md bg-surface-100 text-ink text-xs font-medium border border-gray-200"
                  >
                    {field}
                  </span>
                ))}
              </div>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
};
