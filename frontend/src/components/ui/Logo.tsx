import { Link } from "react-router";

/**
 * The mark: a globe reduced to one meridian and one parallel, with a single
 * persimmon point on its edge, the place you're heading. An atlas, not a gauge.
 */
export function LogoMark({ size = 24, tone = "ink" }: { size?: number; tone?: "ink" | "paper" }) {
  const stroke = tone === "paper" ? "var(--color-paper)" : "var(--color-ink)";
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11.5" cy="12.5" r="9" stroke={stroke} strokeWidth="1.9" />
      <ellipse cx="11.5" cy="12.5" rx="3.9" ry="9" stroke={stroke} strokeWidth="1.5" />
      <path d="M2.8 12.5h17.4" stroke={stroke} strokeWidth="1.5" />
      <circle cx="19.2" cy="5.2" r="3.4" fill="var(--color-persimmon)" stroke={tone === "paper" ? "var(--color-ink)" : "var(--color-ivory)"} strokeWidth="1.6" />
    </svg>
  );
}

export function Logo({ to = "/", tone = "ink" }: { to?: string; tone?: "ink" | "paper" }) {
  return (
    <Link
      to={to}
      className={`inline-flex items-center gap-2 rounded-md font-display text-[18px] font-bold tracking-[-0.03em] ${
        tone === "paper" ? "text-paper" : "text-ink"
      }`}
    >
      <LogoMark tone={tone} />
      Opportunity Hub
    </Link>
  );
}
