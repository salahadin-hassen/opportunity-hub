import React from 'react';
import { Check, AlertTriangle, X, Clock } from 'lucide-react';
import { EligibilityStatus } from '../../types/opportunity';

interface StatusBadgeProps {
  status: EligibilityStatus | 'expired' | 'approaching';
  size?: 'sm' | 'md' | 'lg';
  customText?: string;
  showIcon?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'md',
  customText,
  showIcon = true
}) => {
  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs font-medium gap-1',
    md: 'px-2.5 py-1 text-xs font-semibold gap-1.5',
    lg: 'px-3 py-1.5 text-sm font-semibold gap-2',
  }[size];

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-3.5 h-3.5',
    lg: 'w-4 h-4',
  }[size];

  switch (status) {
    case 'eligible':
      return (
        <span className={`inline-flex items-center rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200/80 ${sizeClasses}`}>
          {showIcon && <Check className={`${iconSizes} text-emerald-600 stroke-[2.5]`} />}
          <span>{customText || 'Eligible'}</span>
        </span>
      );

    case 'potential':
      return (
        <span className={`inline-flex items-center rounded-full bg-amber-50 text-amber-800 border border-amber-200/80 ${sizeClasses}`}>
          {showIcon && <AlertTriangle className={`${iconSizes} text-amber-600 stroke-[2.2]`} />}
          <span>{customText || 'Potential match'}</span>
        </span>
      );

    case 'not-eligible':
      return (
        <span className={`inline-flex items-center rounded-full bg-rose-50 text-rose-800 border border-rose-200/80 ${sizeClasses}`}>
          {showIcon && <X className={`${iconSizes} text-rose-600 stroke-[2.5]`} />}
          <span>{customText || 'Not eligible'}</span>
        </span>
      );

    case 'approaching':
      return (
        <span className={`inline-flex items-center rounded-full bg-orange-50 text-orange-800 border border-orange-200/80 ${sizeClasses}`}>
          {showIcon && <Clock className={`${iconSizes} text-orange-600 stroke-[2]`} />}
          <span>{customText || 'Deadline soon'}</span>
        </span>
      );

    case 'expired':
      return (
        <span className={`inline-flex items-center rounded-full bg-gray-100 text-gray-700 border border-gray-200 ${sizeClasses}`}>
          {showIcon && <X className={`${iconSizes} text-gray-500 stroke-[2]`} />}
          <span>{customText || 'Expired'}</span>
        </span>
      );

    default:
      return null;
  }
};
