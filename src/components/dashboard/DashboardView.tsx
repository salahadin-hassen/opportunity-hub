import React, { useState, useMemo } from 'react';
import { 
  Search, 
  SlidersHorizontal, 
  ArrowRight, 
  CheckCircle2, 
  Circle, 
  Sparkles, 
  ChevronLeft, 
  ChevronRight,
  Filter,
  Layers,
  GraduationCap
} from 'lucide-react';
import { Opportunity, StudentProfile, OpportunityCategory } from '../../types/opportunity';
import { OpportunityCard } from './OpportunityCard';
import { DeadlineAlertBanner, NoResultsState } from '../common/SystemStates';

interface DashboardViewProps {
  opportunities: Opportunity[];
  student: StudentProfile;
  savedOpportunityIds: string[];
  onToggleSave: (id: string, e: React.MouseEvent) => void;
  onSelectOpportunity: (id: string) => void;
  onGoToProfile: () => void;
  onGoToOnboarding: () => void;
  demoEmptyState?: boolean;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  opportunities,
  student,
  savedOpportunityIds,
  onToggleSave,
  onSelectOpportunity,
  onGoToProfile,
  onGoToOnboarding,
  demoEmptyState = false
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<OpportunityCategory>('All');
  const [sortOption, setSortOption] = useState<'best_match' | 'deadline' | 'funding'>('best_match');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 6;

  // Filter and sort opportunities
  const filteredAndSortedOpportunities = useMemo(() => {
    let result = opportunities.filter(opp => {
      // Exclude expired from general active list or keep Rhodes marked as expired
      const matchesCategory = selectedCategory === 'All' || opp.category === selectedCategory;
      const matchesSearch = 
        opp.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        opp.organization.toLowerCase().includes(searchQuery.toLowerCase()) ||
        opp.location.toLowerCase().includes(searchQuery.toLowerCase()) ||
        opp.fields.some(f => f.toLowerCase().includes(searchQuery.toLowerCase()));

      return matchesCategory && matchesSearch;
    });

    // Sorting
    result.sort((a, b) => {
      if (sortOption === 'best_match') {
        const evalA = a.evaluateEligibility(student);
        const evalB = b.evaluateEligibility(student);

        // Score: eligible = 3, potential = 2, not-eligible = 1
        const scoreA = evalA.status === 'eligible' ? 3 : evalA.status === 'potential' ? 2 : 1;
        const scoreB = evalB.status === 'eligible' ? 3 : evalB.status === 'potential' ? 2 : 1;
        if (scoreB !== scoreA) return scoreB - scoreA;
        return a.deadline.localeCompare(b.deadline);
      } else if (sortOption === 'deadline') {
        return a.deadline.localeCompare(b.deadline);
      } else if (sortOption === 'funding') {
        const fundingRank: Record<string, number> = {
          'Fully funded': 4,
          'Paid': 3,
          'Stipend': 2,
          'Funded': 1
        };
        return (fundingRank[b.funding] || 0) - (fundingRank[a.funding] || 0);
      }
      return 0;
    });

    return result;
  }, [opportunities, student, searchQuery, selectedCategory, sortOption]);

  // Pagination calculation
  const totalCount = filteredAndSortedOpportunities.length;
  const totalPages = Math.ceil(totalCount / itemsPerPage) || 1;
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedOpportunities = filteredAndSortedOpportunities.slice(
    startIndex,
    startIndex + itemsPerPage
  );

  // Eligible count for header
  const eligibleMatchCount = opportunities.filter(
    opp => opp.evaluateEligibility(student).status === 'eligible'
  ).length;

  // Approaching deadline check (Fulbright is in 18 days)
  const approachingOpp = opportunities.find(opp => opp.isApproachingDeadline);

  // Categories list
  const categories: OpportunityCategory[] = [
    'All',
    'Scholarships',
    'Internships',
    'Research',
    'Fellowships',
    'Hackathons'
  ];

  // EMPTY STATE DEMONSTRATION (When user has no profile or toggled)
  if (demoEmptyState) {
    const checklistSteps = [
      { name: 'Account created', completed: true },
      { name: 'Personal information', completed: true },
      { name: 'Education & coursework', completed: false },
      { name: 'Test scores (IELTS / GRE)', completed: false },
      { name: 'Skills & frameworks', completed: false },
      { name: 'Academic documents', completed: false },
    ];

    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-8 sm:p-12 text-center">
          <div className="w-16 h-16 rounded-2xl bg-accent-soft flex items-center justify-center text-accent mx-auto mb-5">
            <GraduationCap className="w-8 h-8" />
          </div>

          <h2 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight mb-2">
            No matches yet — complete your profile to start matching against opportunities
          </h2>
          <p className="text-sm sm:text-base text-grayText-600 max-w-lg mx-auto mb-8">
            Unlike generic job boards, Opportunity Hub calculates your exact eligibility by comparing your transcript, GPA, and test scores against official sponsor rules.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10">
            <button
              onClick={onGoToOnboarding}
              className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-semibold px-6 py-3 rounded-xl shadow-sm hover:shadow transition-all"
            >
              <span>Build your profile</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => {}}
              className="text-sm font-semibold text-grayText-600 hover:text-accent underline transition-colors"
            >
              Or explore all opportunities
            </button>
          </div>

          {/* Completion Checklist */}
          <div className="border-t border-gray-100 pt-8 max-w-2xl mx-auto text-left">
            <h4 className="text-xs font-bold uppercase tracking-wider text-grayText-600 font-mono mb-4 text-center">
              Profile Completion Checklist
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {checklistSteps.map((step, idx) => (
                <div 
                  key={idx} 
                  className={`flex items-center gap-2.5 p-3 rounded-xl border text-xs font-medium ${
                    step.completed 
                      ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900' 
                      : 'bg-surface-50 border-gray-200 text-grayText-600'
                  }`}
                >
                  {step.completed ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  ) : (
                    <Circle className="w-4 h-4 text-grayText-400 shrink-0" />
                  )}
                  <span>{step.name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-16">
      {/* Approaching Deadline Alert Banner */}
      {approachingOpp && (
        <DeadlineAlertBanner
          opportunityName={approachingOpp.name}
          daysRemaining={18}
          deadlineDate={approachingOpp.deadlineFormatted}
          onView={() => onSelectOpportunity(approachingOpp.id)}
        />
      )}

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        
        {/* Header: "Your opportunities" + "N opportunities match your profile." */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 text-xs font-semibold mb-2.5 border border-emerald-200/80">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>Deterministic Eligibility Engine Active</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-ink tracking-tight">
              Your opportunities
            </h1>
            <p className="mt-1 text-sm sm:text-base text-grayText-600">
              <strong className="text-ink font-semibold font-mono">{eligibleMatchCount}</strong> opportunities match your profile with 100% satisfied criteria.
            </p>
          </div>

          {/* Student Profile Quick Snapshot Pill */}
          <div className="bg-white rounded-xl border border-gray-200 p-3 shadow-subtle flex items-center gap-4 text-xs font-mono">
            <div>
              <span className="text-grayText-400 block text-[10px] uppercase font-bold">Matched Profile</span>
              <span className="font-semibold text-ink">{student.education.university}</span>
            </div>
            <div className="h-6 w-px bg-gray-200" />
            <div>
              <span className="text-grayText-400 block text-[10px] uppercase font-bold">GPA</span>
              <span className="font-bold text-accent">{student.education.gpa.toFixed(2)} / 4.00</span>
            </div>
            <div className="h-6 w-px bg-gray-200" />
            <div>
              <span className="text-grayText-400 block text-[10px] uppercase font-bold">Graduation</span>
              <span className="font-bold text-ink">{student.education.graduationYear}</span>
            </div>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-subtle p-4 mb-8">
          <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
            
            {/* Search Bar */}
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-grayText-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                placeholder="Search opportunities by title, organization, country, or field..."
                className="w-full pl-10 pr-4 py-2.5 text-sm bg-surface-50 border border-gray-200 rounded-xl focus:bg-white focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/15 transition-all text-ink placeholder:text-grayText-400"
              />
            </div>

            {/* Sort Dropdown */}
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs font-medium text-grayText-600 whitespace-nowrap">Sort:</span>
              <select
                value={sortOption}
                onChange={e => setSortOption(e.target.value as any)}
                aria-label="Sort opportunities"
                className="bg-surface-50 border border-gray-200 text-xs sm:text-sm font-medium text-ink rounded-xl px-3 py-2 focus:outline-none focus:border-accent cursor-pointer"
              >
                <option value="best_match">Best match (Eligible first)</option>
                <option value="deadline">Deadline (Soonest)</option>
                <option value="funding">Funding (Highest)</option>
              </select>
            </div>
          </div>

          {/* Category Filter Tabs (All / Scholarships / Internships / Research / Fellowships / Hackathons) */}
          <div className="flex items-center gap-1.5 mt-4 pt-3 border-t border-gray-100 overflow-x-auto pb-1 scrollbar-none">
            {categories.map(cat => (
              <button
                key={cat}
                onClick={() => {
                  setSelectedCategory(cat);
                  setCurrentPage(1);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                  selectedCategory === cat
                    ? 'bg-accent text-white shadow-sm'
                    : 'text-grayText-600 hover:text-ink hover:bg-surface-100'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Opportunity Card Grid or No-Results State */}
        {filteredAndSortedOpportunities.length === 0 ? (
          <NoResultsState
            query={searchQuery}
            category={selectedCategory !== 'All' ? selectedCategory : undefined}
            onResetFilters={() => {
              setSearchQuery('');
              setSelectedCategory('All');
            }}
          />
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
              {paginatedOpportunities.map(opp => (
                <OpportunityCard
                  key={opp.id}
                  opportunity={opp}
                  student={student}
                  isSaved={savedOpportunityIds.includes(opp.id)}
                  onToggleSave={onToggleSave}
                  onSelect={onSelectOpportunity}
                />
              ))}
            </div>

            {/* Pagination: "Showing 1-6 of N", Previous/Next */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-gray-200">
              <p className="text-xs sm:text-sm text-grayText-600 font-mono">
                Showing{' '}
                <span className="font-semibold text-ink">{startIndex + 1}</span>–
                <span className="font-semibold text-ink">
                  {Math.min(startIndex + itemsPerPage, totalCount)}
                </span>{' '}
                of <span className="font-semibold text-ink">{totalCount}</span> opportunities
              </p>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    currentPage === 1
                      ? 'border-gray-200 text-grayText-400 cursor-not-allowed bg-gray-50'
                      : 'border-gray-300 text-ink hover:bg-surface-50'
                  }`}
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  <span>Previous</span>
                </button>

                <div className="flex items-center gap-1">
                  {Array.from({ length: totalPages }).map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setCurrentPage(i + 1)}
                      className={`w-7 h-7 rounded-lg text-xs font-mono font-medium transition-colors ${
                        currentPage === i + 1
                          ? 'bg-accent text-white'
                          : 'text-grayText-600 hover:bg-gray-100'
                      }`}
                    >
                      {i + 1}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    currentPage === totalPages
                      ? 'border-gray-200 text-grayText-400 cursor-not-allowed bg-gray-50'
                      : 'border-gray-300 text-ink hover:bg-surface-50'
                  }`}
                >
                  <span>Next</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
