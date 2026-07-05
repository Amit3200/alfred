type AlfredMarkProps = {
  size?: number;
  className?: string;
};

/**
 * Alfred brand mark loading the new black & white branding logo.
 */
export function AlfredMark({ size = 36, className }: AlfredMarkProps) {
  return (
    <img
      src="/logo.png"
      alt="Alfred logo"
      width={size}
      height={size}
      className={className}
      style={{ display: "inline-block", objectFit: "contain", borderRadius: 4 }}
    />
  );
}
