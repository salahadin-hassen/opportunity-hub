import type {
  DegreeLevel,
  LocationMode,
  MatchStatus,
  Opportunity,
  OpportunityType,
} from "../api/types";

export const TYPE_LABELS: Record<OpportunityType, string> = {
  scholarship: "Scholarship",
  internship: "Internship",
  fellowship: "Fellowship",
  research_program: "Research program",
  summer_school: "Summer school",
  hackathon: "Hackathon",
  competition: "Competition",
  open_source_program: "Open source",
  grant: "Grant",
  conference: "Conference",
  course: "Course",
  job: "Job",
  other: "Program",
};

export const TYPE_PLURALS: Record<OpportunityType, string> = {
  scholarship: "Scholarships",
  internship: "Internships",
  fellowship: "Fellowships",
  research_program: "Research programs",
  summer_school: "Summer schools",
  hackathon: "Hackathons",
  competition: "Competitions",
  open_source_program: "Open source programs",
  grant: "Grants",
  conference: "Conferences",
  course: "Courses",
  job: "Jobs",
  other: "Student programs",
};

export const LOCATION_LABELS: Record<LocationMode, string> = {
  onsite: "On site",
  hybrid: "Hybrid",
  remote: "Remote",
  unknown: "Location varies",
};

export const DEGREE_LABELS: Record<DegreeLevel, string> = {
  high_school: "High school",
  associate: "Associate",
  bachelor: "Bachelor’s",
  master: "Master’s",
  doctorate: "Doctorate",
  other: "Other",
};

export const STATUS_LABELS: Record<MatchStatus, string> = {
  eligible: "Eligible",
  potential_match: "Potential",
  not_eligible: "Not eligible",
  needs_review: "Review",
};

export const STATUS_LONG: Record<MatchStatus, string> = {
  eligible: "Eligible",
  potential_match: "Potential match",
  not_eligible: "Not eligible",
  needs_review: "Needs review",
};

/** Verdict order used for summaries and grouping: most actionable first. */
export const STATUS_ORDER: MatchStatus[] = [
  "eligible",
  "potential_match",
  "needs_review",
  "not_eligible",
];

let regionNames: Intl.DisplayNames | null = null;

export function countryName(code: string): string {
  try {
    regionNames ??= new Intl.DisplayNames(["en"], { type: "region" });
    return regionNames.of(code.toUpperCase()) ?? code.toUpperCase();
  } catch {
    return code.toUpperCase();
  }
}

let languageNames: Intl.DisplayNames | null = null;

export function languageName(code: string): string {
  try {
    languageNames ??= new Intl.DisplayNames(["en"], { type: "language" });
    return languageNames.of(code) ?? code;
  } catch {
    return code;
  }
}

const DAY = 86_400_000;

/** "15 Nov 2026" — dates only: official pages rarely give a time of day. */
export function formatDate(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** Plain calendar dates from the API ("2023-10-01") without timezone drift. */
export function formatPlainDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export type DeadlineInfo = {
  /** Primary label: a date, "Rolling", "No deadline" or "See official page". */
  label: string;
  /** Secondary label such as "in 16 days" or "closed". */
  relative: string | null;
  /** Milliseconds until the deadline, for sorting; Infinity when open-ended. */
  sortKey: number;
  state: "open" | "soon" | "closed" | "rolling" | "none" | "unknown";
};

export function deadlineInfo(
  opportunity: Pick<Opportunity, "deadline_at" | "deadline_type">,
  now: number = Date.now(),
): DeadlineInfo {
  if (opportunity.deadline_type === "rolling") {
    return { label: "Rolling", relative: "apply any time", sortKey: Number.MAX_SAFE_INTEGER - 2, state: "rolling" };
  }
  if (opportunity.deadline_type === "none") {
    return { label: "No deadline", relative: null, sortKey: Number.MAX_SAFE_INTEGER - 1, state: "none" };
  }
  if (!opportunity.deadline_at) {
    return { label: "See official page", relative: null, sortKey: Number.MAX_SAFE_INTEGER, state: "unknown" };
  }
  const at = new Date(opportunity.deadline_at).getTime();
  const days = Math.ceil((at - now) / DAY);
  const label = formatDate(opportunity.deadline_at);
  if (days < 0) return { label, relative: "closed", sortKey: Number.MAX_SAFE_INTEGER, state: "closed" };
  if (days === 0) return { label, relative: "today", sortKey: at - now, state: "soon" };
  if (days === 1) return { label, relative: "tomorrow", sortKey: at - now, state: "soon" };
  return {
    label,
    relative: `in ${days} days`,
    sortKey: at - now,
    state: days <= 30 ? "soon" : "open",
  };
}

/**
 * Local clock time for a deadline that has one, e.g. "07:59 GMT+3".
 *
 * Date-only deadlines are stored at 12:00 UTC by convention (see the demo
 * seed), so they return ``null`` rather than a time nobody published.
 */
export function deadlineTime(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (date.getUTCHours() === 12 && date.getUTCMinutes() === 0) return null;
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
}

/** True when the deadline label is a calendar date (set in mono like other data). */
export function deadlineIsDate(opportunity: Pick<Opportunity, "deadline_at" | "deadline_type">): boolean {
  return opportunity.deadline_type !== "rolling" && opportunity.deadline_type !== "none" && Boolean(opportunity.deadline_at);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
