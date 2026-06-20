import { AlfredMark } from "./AlfredMark";

type LogoProps = {
  compact?: boolean;
  size?: "sm" | "md" | "lg";
};

const sizes = { sm: 28, md: 36, lg: 52 };

export function Logo({ compact = false, size = "md" }: LogoProps) {
  const px = sizes[size];

  return (
    <div className="alfred-logo">
      <AlfredMark size={px} className="alfred-logo-icon" />
      {!compact && (
        <div className="alfred-logo-text">
          <span className="alfred-logo-title">Alfred</span>
          <span className="alfred-logo-subtitle">Agent console</span>
        </div>
      )}
    </div>
  );
}
