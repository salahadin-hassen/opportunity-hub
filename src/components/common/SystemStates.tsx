import React from 'react';
import { 
  Loader2, 
  SearchX, 
  AlertCircle, 
  FileWarning, 
  Clock, 
  CalendarX, 
  RefreshCw,
  ArrowRight
} from 'lucide-react';

interface LoadingStateProps {
  message?: string;
  submessage?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = "Analyzing opportunities... usually takes a few seconds",
  submessage = "Evaluating criteria rules against your academic profile..."
}) => (
  <div className="flex flex-col items-center justify-center p-12 text-center bg-white rounded-xl border border-gray-100 shadow-subtle min-h-[320px]">
    <div className="relative mb-5">
      <div className="w-14 h-14 rounded-full bg-accent-soft flex items-center justify-center">
        <Loader2 className="w-7 h-7 text-accent animate-spin" />
      </div>
      <div className="absolute -top-1 -right-1 w-4 h-4 bg-emerald-500 rounded-full border-2 border-white animate-pulse" />
    </div>
    <h3 className="text-base font-semibold text-ink mb-1.5">{message}</h3>
    <p className="text-sm text-grayText-600 max-w-md">{submessage}</p>
    
    {/* Micro progress skeleton */}
    <div className="w-64 h-1.5 bg-gray-100 rounded-full mt-6 overflow-hidden">
      <div className="h-full bg-accent rounded-full animate-soft-pulse w-3/4" />
    </div>
  </div>
);

interface NoResultsStateProps {
  query?: string;
  category?: string;
  onResetFilters?: () => void;
}

export const NoResultsState: React.FC<NoResultsStateProps> = ({
  query,
  category,
  onResetFilters
}) => (
  <div className="flex flex-col items-center justify-center p-12 text-center bg-white rounded-xl border border-gray-100 shadow-subtle min-h-[320px]">
    <div className="w-14 h-14 rounded-full bg-gray-100 flex items-center justify-center mb-4">
      <SearchX className="w-7 h-7 text-grayText-400" />
    </div>
    <h3 className="text-base font-semibold text-ink mb-1.5">No matches found</h3>
    <p className="text-sm text-grayText-600 max-w-md mb-5">
      {query 
        ? `We couldn't find any opportunities matching "${query}". Try adjusting your keywords or clearing category filters.`
        : "No matches found — try adjusting your filters or completing your profile."}
    </p>
    {onResetFilters && (
      <button
        onClick={onResetFilters}
        className="inline-flex items-center gap-2 px-4 py-2 bg-surface-100 hover:bg-surface-200 text-ink text-sm font-medium rounded-lg transition-colors"
      >
        <RefreshCw className="w-4 h-4 text-grayText-600" />
        <span>Reset all filters</span>
      </button>
    )}
  </div>
);

interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = "Something went wrong",
  description = "Something went wrong — try again. Our verification engine encountered a temporary network delay.",
  onRetry
}) => (
  <div className="flex flex-col items-center justify-center p-12 text-center bg-white rounded-xl border border-rose-100 shadow-subtle min-h-[320px]">
    <div className="w-14 h-14 rounded-full bg-rose-50 flex items-center justify-center mb-4">
      <AlertCircle className="w-7 h-7 text-rose-600" />
    </div>
    <h3 className="text-base font-semibold text-ink mb-1.5">{title}</h3>
    <p className="text-sm text-grayText-600 max-w-md mb-5">{description}</p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-lg shadow-sm transition-colors"
      >
        <RefreshCw className="w-4 h-4" />
        <span>Try again</span>
      </button>
    )}
  </div>
);

interface UploadFailedProps {
  fileName?: string;
  errorMessage?: string;
  onDismiss?: () => void;
}

export const UploadFailedState: React.FC<UploadFailedProps> = ({
  fileName = "document.xyz",
  errorMessage = "Unsupported format — try another file. Supported: PDF, DOCX · Max 10MB.",
  onDismiss
}) => (
  <div className="p-4 rounded-xl bg-rose-50 border border-rose-200/80 flex items-start justify-between gap-3 text-left">
    <div className="flex items-start gap-3">
      <div className="w-9 h-9 rounded-lg bg-rose-100 flex items-center justify-center shrink-0 mt-0.5">
        <FileWarning className="w-5 h-5 text-rose-600" />
      </div>
      <div>
        <p className="text-sm font-semibold text-rose-900">Upload failed for {fileName}</p>
        <p className="text-xs text-rose-700 mt-0.5">{errorMessage}</p>
      </div>
    </div>
    {onDismiss && (
      <button 
        onClick={onDismiss}
        className="text-xs font-semibold text-rose-800 hover:text-rose-950 px-2 py-1 hover:bg-rose-100 rounded transition-colors"
      >
        Dismiss
      </button>
    )}
  </div>
);

interface DeadlineAlertBannerProps {
  opportunityName: string;
  daysRemaining: number;
  deadlineDate: string;
  onView?: () => void;
}

export const DeadlineAlertBanner: React.FC<DeadlineAlertBannerProps> = ({
  opportunityName,
  daysRemaining,
  deadlineDate,
  onView
}) => (
  <div className="w-full bg-gradient-to-r from-orange-500/10 via-amber-500/10 to-orange-500/10 border-y border-amber-300/80 px-4 sm:px-6 py-2.5">
    <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs sm:text-sm">
      <div className="flex items-center gap-2 text-amber-900 font-medium">
        <Clock className="w-4 h-4 text-amber-600 shrink-0" />
        <span>
          <strong className="font-semibold text-amber-950">⚠ {opportunityName}</strong> deadline in{' '}
          <span className="font-mono font-bold text-amber-950">{daysRemaining} days</span> ({deadlineDate})
        </span>
      </div>
      {onView && (
        <button
          onClick={onView}
          className="inline-flex items-center gap-1 font-semibold text-accent hover:text-accent-hover text-xs uppercase tracking-wider transition-colors shrink-0"
        >
          <span>View checklist</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  </div>
);

interface ExpiredStateProps {
  programName: string;
  nextCycleDate?: string;
}

export const ExpiredState: React.FC<ExpiredStateProps> = ({
  programName,
  nextCycleDate = "June 2027"
}) => (
  <div className="p-4 rounded-xl bg-gray-100 border border-gray-300 text-left flex items-start gap-3">
    <div className="w-9 h-9 rounded-lg bg-gray-200 flex items-center justify-center shrink-0">
      <CalendarX className="w-5 h-5 text-gray-600" />
    </div>
    <div>
      <div className="flex items-center gap-2">
        <span className="px-2 py-0.5 rounded bg-gray-800 text-white font-mono text-[10px] font-bold tracking-wide">
          EXPIRED
        </span>
        <span className="text-xs font-semibold text-gray-800">{programName}</span>
      </div>
      <p className="text-xs text-grayText-600 mt-1">
        This program is closed. Next cycle begins <strong className="font-mono text-ink">{nextCycleDate}</strong>.
      </p>
    </div>
  </div>
);
