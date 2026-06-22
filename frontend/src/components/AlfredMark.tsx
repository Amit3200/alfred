type AlfredMarkProps = {
  size?: number;
  className?: string;
};

/**
 * Alfred brand mark — bow tie, collar, and serving tray.
 * Evokes the butler: ready to serve, formal, precise.
 */
export function AlfredMark({ size = 36, className }: AlfredMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden
    >
      <rect width="64" height="64" className="alfred-mark-bg" />

      {/* shirt collar */}
      <path d="M20 22h24l-2 4H22l-2-4z" className="alfred-mark-collar" />

      {/* bow tie — left wing */}
      <path d="M32 36 14 28c-2-1-2-4 0-5l18 8v5z" className="alfred-mark-tie" />
      {/* bow tie — right wing */}
      <path d="M32 36 50 28c2-1 2-4 0-5L32 31v5z" className="alfred-mark-tie" />
      {/* knot */}
      <g>
        <rect x="27" y="29" width="10" height="9" rx="2" className="alfred-mark-knot" />
        <path
          d="M 28.5 33.5 h 2 l 1 2 l 1 -5 l 1 5.5 l 0.75 -2.5 h 1.25"
          className="alfred-mark-knot-heartbeat"
          strokeWidth="0.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>

      {/* serving tray */}
      <path
        d="M18 46h28"
        className="alfred-mark-tray"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M22 46v2M42 46v2"
        className="alfred-mark-tray"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
