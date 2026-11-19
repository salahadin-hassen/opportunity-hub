/** Small ink details shared by the landing page. */

/** The flick marks that appear around a stamp button on hover (see .btn-stamp .ticks). */
export function Ticks() {
  return (
    <svg className="ticks" viewBox="0 0 120 60" preserveAspectRatio="none" aria-hidden="true">
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none">
        <path d="M5 13 L11 21" vectorEffect="non-scaling-stroke" />
        <path d="M2 31 L10 30" vectorEffect="non-scaling-stroke" />
        <path d="M115 13 L109 21" vectorEffect="non-scaling-stroke" />
        <path d="M118 31 L110 30" vectorEffect="non-scaling-stroke" />
      </g>
    </svg>
  );
}
