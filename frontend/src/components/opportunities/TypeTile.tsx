import {
  Award,
  BookOpen,
  Briefcase,
  Code2,
  FlaskConical,
  GraduationCap,
  Lightbulb,
  Mic,
  Sparkles,
  Sun,
  Trophy,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import type { OpportunityType } from "../../api/types";
import { TYPE_LABELS } from "../../lib/format";

/**
 * Each opportunity type has a colour and an icon. Opportunities carry no
 * logos (we never invent institutional marks), so this typographic system is
 * how a listing gets its identity.
 */
export const TYPE_STYLE: Record<OpportunityType, { icon: LucideIcon; tile: string; text: string; accent: string }> = {
  scholarship: { icon: GraduationCap, tile: "bg-cobalt", text: "text-snow", accent: "text-lime" },
  internship: { icon: Briefcase, tile: "bg-persimmon", text: "text-night", accent: "text-snow" },
  research_program: { icon: FlaskConical, tile: "bg-lime", text: "text-night", accent: "text-cobalt-fixed" },
  fellowship: { icon: Award, tile: "bg-night ring-1 ring-inset ring-night-edge", text: "text-snow", accent: "text-lime" },
  open_source_program: { icon: Code2, tile: "bg-cream", text: "text-ink", accent: "text-persimmon-deep" },
  summer_school: { icon: Sun, tile: "bg-potential-wash", text: "text-ink", accent: "text-potential-ink" },
  hackathon: { icon: Lightbulb, tile: "bg-persimmon-wash", text: "text-ink", accent: "text-persimmon-deep" },
  competition: { icon: Trophy, tile: "bg-cobalt-wash", text: "text-ink", accent: "text-cobalt-deep" },
  grant: { icon: Wallet, tile: "bg-eligible-wash", text: "text-ink", accent: "text-eligible-ink" },
  conference: { icon: Mic, tile: "bg-review-wash", text: "text-ink", accent: "text-review-ink" },
  course: { icon: BookOpen, tile: "bg-cream", text: "text-ink", accent: "text-cobalt-deep" },
  job: { icon: Briefcase, tile: "bg-sand", text: "text-ink", accent: "text-ink-soft" },
  other: { icon: Sparkles, tile: "bg-sand", text: "text-ink", accent: "text-persimmon-deep" },
};

/**
 * A monogram from the host's own name, set in type, never a logo: the host's
 * acronym when it leads with one (EPFL, ETH, NASA), the initials of a long
 * name (King Abdullah University of Science and Technology: KAUST), otherwise
 * the first letters of up to two words.
 */
export function monogram(host: string | null | undefined): string {
  const words = (host ?? "").replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/).filter((word) => word && !/^(of|the|and|for|de|du|la)$/i.test(word));
  if (words.length === 0) return "··";
  if (/^[A-Z]{2,5}$/.test(words[0]!)) return words[0]!;
  if (words.length >= 4) return words.slice(0, 5).map((word) => word[0]!.toUpperCase()).join("");
  return words.slice(0, 2).map((word) => word[0]!.toUpperCase()).join("");
}

/** Monogram size relative to its box, so five letters fit where two do. */
export function monogramScale(text: string): number {
  return text.length <= 2 ? 0.3 : text.length === 3 ? 0.25 : text.length === 4 ? 0.21 : 0.18;
}

export function TypeTile({ type, host, size = 48 }: { type: OpportunityType; host?: string | null; size?: number }) {
  const style = TYPE_STYLE[type];
  const Icon = style.icon;
  return (
    <span
      className={`relative inline-flex shrink-0 items-end justify-start overflow-hidden rounded-[10px] p-1.5 ${style.tile} ${style.text}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <Icon size={size * 0.3} className={`absolute right-1.5 top-1.5 ${style.accent}`} strokeWidth={2} />
      <span className="font-display font-bold leading-none tracking-[-0.03em]" style={{ fontSize: Math.max(10.5, size * monogramScale(monogram(host))) }}>
        {monogram(host)}
      </span>
    </span>
  );
}

export function TypeLabel({ type }: { type: OpportunityType }) {
  const Icon = TYPE_STYLE[type].icon;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[12.5px] font-semibold text-ink">
      <Icon size={13} strokeWidth={2.2} className="text-ink-soft" />
      {TYPE_LABELS[type]}
    </span>
  );
}
