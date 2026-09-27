import React from 'react';
import { 
  Building2, 
  MapPin, 
  Calendar, 
  Bookmark, 
  Check, 
  AlertTriangle, 
  X, 
  ArrowRight,
  Clock,
  ExternalLink
} from 'lucide-react';
import { Opportunity, StudentProfile } from '../../types/opportunity';
import { StatusBadge } from '../common/StatusBadge';

interface OpportunityCardProps {
  opportunity: Opportunity;
  student: StudentProfile;
  isSaved: boolean;
  onToggleSave: (id: string, e: React.MouseEvent) => void;
  onSelect: (id: string) => void;
}

export const OpportunityCard: React.FC<OpportunityCardProps> = ({
  opportunity,
  student,
  isSaved,
  onToggleSave,
  onSelect
}) => {
  const evaluation = opportunity.evaluateEligibility(student);

  // Funding badge styling
  const fundingStyles = {
    'Fully funded': 'bg-emerald-50 text-emerald-800 border-emerald-200',
    'Stipend': 'bg-blue-50 text-blue-800 border-blue-200',
    'Paid': 'bg-purple-50 text-purple-800 border-purple-200',
    'Funded': 'bg-indigo-50 text-indigo-800 border-indigo-200'
  }[opportunity.funding] || 'bg-gray-100 text-gray-800 border-gray-200';

  return (
    <div 
      onClick={() => onSelect(opportunity.id)}
      className="group bg-white rounded-2xl border border-gray-200 hover:border-accent/50 shadow-card hover:shadow-elevated transition-all duration-200 p-5 sm:p-6 cursor-pointer flex flex-col justify-between relative overflow-hidden"
    >
      {/* Top row: Title, Org, and Save Button */}
      <div>
        <div className="flex items-start justify-between gap-4 mb-2.5">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border font-mono ${fundingStyles}`}>
                {opportunity.funding}
              </span>
              <span className="text-xs text-grayText-600 font-medium">
                {opportunity.category}
              </span>
              {opportunity.isApproachingDeadline && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-orange-50 text-orange-800 border border-orange-200 text-[10px] font-bold uppercase font-mono tracking-wider animate-pulse">
                  <Clock className="w-3 h-3" />
                  <span>Approaching Deadline</span>
                </span>
              )}
            </div>

            <h3 className="text-lg font-bold text-ink group-hover:text-accent transition-colors line-clamp-1">
              {opportunity.name}
            </h3>
          </div>

          <button
            onClick={(e) => onToggleSave(opportunity.id, e)}
            title={isSaved ? "Remove from saved" : "Save opportunity"}
            className={`p-2 rounded-xl transition-all ${
              isSaved 
                ? 'bg-accent-soft text-accent hover:bg-indigo-100' 
                : 'text-grayText-400 hover:text-ink hover:bg-gray-100'
            }`}
          >
            <Bookmark className={`w-4 h-4 ${isSaved ? 'fill-accent' : ''}`} />
          </button>
        </div>

        {/* Subhead: org · type · location */}
        <p className="text-xs text-grayText-600 font-medium mb-4 flex items-center gap-1.5 flex-wrap">
          <span className="font-semibold text-ink">{opportunity.organization}</span>
          <span>·</span>
          <span>{opportunity.type}</span>
          <span>·</span>
          <span className="inline-flex items-center gap-0.5 text-grayText-600">
            <MapPin className="w-3 h-3" />
            {opportunity.location}
          </span>
        </p>

        {/* Criteria Checklist Row (✓ met / ⚠ uncertain / ✕ unmet) */}
        <div className="bg-surface-50 rounded-xl p-3 border border-gray-100 mb-4">
          <div className="text-[10px] uppercase font-bold tracking-wider text-grayText-600 mb-2 font-mono flex items-center justify-between">
            <span>Eligibility Checklist</span>
            <span className="text-grayText-400 font-normal">
              {evaluation.criteriaChecks.length} criteria evaluated
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {evaluation.criteriaChecks.map((criterion) => {
              if (criterion.status === 'met') {
                return (
                  <span
                    key={criterion.id}
                    title={`${criterion.label}: Met`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200/80 text-[11px] font-medium"
                  >
                    <Check className="w-3 h-3 text-emerald-600 stroke-[2.5]" />
                    <span>{criterion.shortLabel}</span>
                  </span>
                );
              } else if (criterion.status === 'uncertain') {
                return (
                  <span
                    key={criterion.id}
                    title={`${criterion.label}: Uncertain`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200/80 text-[11px] font-medium"
                  >
                    <AlertTriangle className="w-3 h-3 text-amber-600 stroke-[2.2]" />
                    <span>{criterion.shortLabel}</span>
                  </span>
                );
              } else {
                return (
                  <span
                    key={criterion.id}
                    title={`${criterion.label}: Unmet`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-50 text-rose-800 border border-rose-200/80 text-[11px] font-medium"
                  >
                    <X className="w-3 h-3 text-rose-600 stroke-[2.5]" />
                    <span>{criterion.shortLabel}</span>
                  </span>
                );
              }
            })}
          </div>
        </div>
      </div>

      {/* Bottom Footer: Eligibility badge & Deadline */}
      <div className="pt-3 border-t border-gray-100 flex items-center justify-between gap-2 mt-auto">
        <StatusBadge status={evaluation.status} size="sm" />

        <div className="flex items-center gap-2">
          <div className="text-right">
            <p className="text-[10px] uppercase font-bold text-grayText-600 font-mono tracking-wider">
              Deadline
            </p>
            <p className="text-xs font-semibold text-ink font-mono">
              {opportunity.deadlineFormatted}
            </p>
          </div>
          <div className="w-7 h-7 rounded-lg bg-surface-100 group-hover:bg-accent group-hover:text-white flex items-center justify-center text-grayText-600 transition-colors">
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>
      </div>
    </div>
  );
};
