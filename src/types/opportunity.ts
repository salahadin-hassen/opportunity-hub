export type EligibilityStatus = 'eligible' | 'potential' | 'not-eligible';

export type CriterionStatus = 'met' | 'uncertain' | 'unmet';

export type FundingType = 'Fully funded' | 'Stipend' | 'Paid' | 'Funded';

export type OpportunityCategory = 
  | 'All' 
  | 'Scholarships' 
  | 'Internships' 
  | 'Research' 
  | 'Fellowships' 
  | 'Hackathons';

export interface WorkPosition {
  id: string;
  title: string;
  organization: string;
  startDate: string;
  endDate: string;
  description?: string;
}

export interface DocumentFile {
  id: string;
  name: string;
  type: 'transcript' | 'cv' | 'certificate' | 'test_sheet';
  size: string;
  uploadedAt: string;
  status: 'analyzed' | 'ready' | 'analyzing' | 'error';
}

export interface StudentProfile {
  personal: {
    name: string;
    country: string;
    city: string;
    dateOfBirth: string;
    email: string;
  };
  education: {
    university: string;
    degree: string;
    gpa: number;
    maxGpa: number;
    graduationYear: number;
    field: string;
    relevantCourses: string[];
  };
  testScores: {
    ielts: number | null;
    gre: {
      total: number;
      verbal: number;
      quant: number;
      analyticalWriting: number;
    } | null;
  };
  skills: string[];
  experience: WorkPosition[];
  documents: DocumentFile[];
  preferences: {
    preferredLocations: string[];
    fundingPreference: string;
    availableFrom: string;
  };
}

export interface CriterionCheck {
  id: string;
  label: string;
  shortLabel: string; // e.g. "GPA", "English", "Nationality", "Work exp."
  required: string;
  studentValue: string;
  status: CriterionStatus;
  note?: string;
  sourceSection?: string;
}

export interface Opportunity {
  id: string;
  name: string;
  organization: string;
  category: Exclude<OpportunityCategory, 'All'>;
  type: string;
  location: string;
  funding: FundingType;
  duration: string;
  deadline: string; // ISO format: YYYY-MM-DD
  deadlineFormatted: string;
  isApproachingDeadline?: boolean;
  isExpired?: boolean;
  nextCycleDate?: string;
  source: {
    name: string;
    url: string;
    lastVerified: string;
  };
  about: string;
  covers: string[];
  fields: string[];
  // Function to evaluate this opportunity against student profile
  evaluateEligibility: (student: StudentProfile) => {
    status: EligibilityStatus;
    criteriaChecks: CriterionCheck[];
    summaryBadgeText: string;
    unmetCount: number;
    uncertainCount: number;
  };
}

export type ApplicationProgress = 'Not started' | 'In progress' | 'Applied';

export interface SavedOpportunityRecord {
  opportunityId: string;
  savedAt: string;
  applicationStatus: ApplicationProgress;
  notes?: string;
}
