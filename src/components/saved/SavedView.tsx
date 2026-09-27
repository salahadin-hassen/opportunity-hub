import React, { useState } from 'react';
import { 
  Bookmark, 
  Trash2, 
  ExternalLink, 
  Clock, 
  ArrowRight, 
  CheckCircle2, 
  Filter,
  Check
} from 'lucide-react';
import { Opportunity, StudentProfile, ApplicationProgress } from '../../types/opportunity';
import { StatusBadge } from '../common/StatusBadge';

interface SavedViewProps {
  savedOpportunities: Opportunity[];
  student: StudentProfile;
  applicationStatuses: Record<string, ApplicationProgress>;
  onUpdateApplicationStatus: (oppId: string, status: ApplicationProgress) => void;
  onRemoveSaved: (oppId: string) => void;
  onSelectOpportunity: (oppId: string) => void;
  onBrowseOpportunities: () => void;
}

export const SavedView: React.FC<SavedViewProps> = ({
  savedOpportunities,
  student,
  applicationStatuses,
  onUpdateApplicationStatus,
  onRemoveSaved,
  onSelectOpportunity,
  onBrowseOpportunities
}) => {
  const [filterTab, setFilterTab] = useState<'all' | 'eligible' | 'approaching'>('all');

  const filteredOpportunities = savedOpportunities.filter(opp => {
    const evaluation = opp.evaluateEligibility(student);
    if (filterTab === 'eligible') {
      return evaluation.status === 'eligible';
    } else if (filterTab === 'approaching') {
      return opp.isApproachingDeadline;
    }
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10 min-h-screen">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent-soft text-accent text-xs font-semibold uppercase tracking-wider mb-2">
            <Bookmark className="w-3.5 h-3.5" />
            <span>Tracked Opportunities</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-ink tracking-tight">
            Saved opportunities
          </h1>
          <p className="mt-1 text-sm text-grayText-600">
            <strong className="font-mono text-ink font-semibold">{savedOpportunities.length}</strong> opportunities saved to your shortlist.
          </p>
        </div>

        {/* Filter tabs: All / Eligible / Approaching deadline */}
        <div className="flex items-center gap-1 bg-surface-100 p-1 rounded-xl self-start sm:self-auto border border-gray-200">
          <button
            onClick={() => setFilterTab('all')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              filterTab === 'all'
                ? 'bg-white text-ink shadow-xs'
                : 'text-grayText-600 hover:text-ink'
            }`}
          >
            All ({savedOpportunities.length})
          </button>
          <button
            onClick={() => setFilterTab('eligible')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              filterTab === 'eligible'
                ? 'bg-white text-ink shadow-xs'
                : 'text-grayText-600 hover:text-ink'
            }`}
          >
            Eligible
          </button>
          <button
            onClick={() => setFilterTab('approaching')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              filterTab === 'approaching'
                ? 'bg-white text-ink shadow-xs'
                : 'text-grayText-600 hover:text-ink'
            }`}
          >
            Approaching deadline
          </button>
        </div>
      </div>

      {/* Empty State */}
      {filteredOpportunities.length === 0 ? (
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-12 text-center max-w-lg mx-auto">
          <div className="w-14 h-14 rounded-2xl bg-surface-100 flex items-center justify-center text-grayText-400 mx-auto mb-4">
            <Bookmark className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-ink mb-1">No saved opportunities here</h3>
          <p className="text-xs sm:text-sm text-grayText-600 mb-6">
            Bookmark opportunities from the Discover catalog to monitor deadlines and track application stages.
          </p>
          <button
            onClick={onBrowseOpportunities}
            className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-xs sm:text-sm font-semibold px-5 py-2.5 rounded-xl transition-all"
          >
            <span>Explore opportunities</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      ) : (
        /* Saved Table */
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-50 border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-grayText-600 font-mono">
                  <th className="py-3.5 px-4 sm:px-6">Opportunity</th>
                  <th className="py-3.5 px-4 sm:px-6">Type</th>
                  <th className="py-3.5 px-4 sm:px-6">Deadline</th>
                  <th className="py-3.5 px-4 sm:px-6">Status</th>
                  <th className="py-3.5 px-4 sm:px-6">Application</th>
                  <th className="py-3.5 px-4 sm:px-6 text-right">Remove</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 text-xs sm:text-sm">
                {filteredOpportunities.map(opp => {
                  const evaluation = opp.evaluateEligibility(student);
                  const currentAppStatus = applicationStatuses[opp.id] || 'Not started';

                  return (
                    <tr key={opp.id} className="hover:bg-surface-50/70 transition-colors">
                      {/* Column 1: Opportunity */}
                      <td className="py-4 px-4 sm:px-6">
                        <div 
                          onClick={() => onSelectOpportunity(opp.id)}
                          className="font-bold text-ink hover:text-accent cursor-pointer transition-colors"
                        >
                          {opp.name}
                        </div>
                        <p className="text-xs text-grayText-600 mt-0.5">
                          {opp.organization} · {opp.location}
                        </p>
                      </td>

                      {/* Column 2: Type */}
                      <td className="py-4 px-4 sm:px-6 font-mono text-xs text-gray-700">
                        {opp.type}
                      </td>

                      {/* Column 3: Deadline */}
                      <td className="py-4 px-4 sm:px-6 font-mono text-xs">
                        <div className="flex items-center gap-1.5">
                          {opp.isApproachingDeadline && (
                            <Clock className="w-3.5 h-3.5 text-orange-600" />
                          )}
                          <span className={opp.isApproachingDeadline ? 'text-orange-950 font-bold' : 'text-ink font-semibold'}>
                            {opp.deadlineFormatted}
                          </span>
                        </div>
                      </td>

                      {/* Column 4: Status */}
                      <td className="py-4 px-4 sm:px-6">
                        <StatusBadge status={evaluation.status} size="sm" />
                      </td>

                      {/* Column 5: Application Status (Dropdown / Toggle) */}
                      <td className="py-4 px-4 sm:px-6">
                        <select
                          value={currentAppStatus}
                          onChange={(e) => onUpdateApplicationStatus(opp.id, e.target.value as ApplicationProgress)}
                          aria-label={`Application status for ${opp.name}`}
                          className="bg-surface-50 border border-gray-200 text-xs font-semibold rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-accent text-ink cursor-pointer"
                        >
                          <option value="Not started">Not started</option>
                          <option value="In progress">In progress</option>
                          <option value="Applied">Applied</option>
                        </select>
                      </td>

                      {/* Column 6: Remove (×) action */}
                      <td className="py-4 px-4 sm:px-6 text-right">
                        <button
                          onClick={() => onRemoveSaved(opp.id)}
                          title="Remove from saved"
                          className="p-1.5 rounded-lg text-grayText-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
};
