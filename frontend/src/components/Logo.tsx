import { AlfredMark } from "./AlfredMark";
import type { PublicBranding } from "../api/client";
import { defaultPublicBranding } from "../branding";

type LogoProps = {
  compact?: boolean;
  size?: "sm" | "md" | "lg";
  branding?: PublicBranding | null;
};

const sizes = { sm: 28, md: 36, lg: 52 };
const companyLogoSizes = { sm: 24, md: 32, lg: 44 };

export function Logo({ compact = false, size = "md", branding }: LogoProps) {
  const profile = branding || defaultPublicBranding();
  const px = sizes[size];
  const companyPx = companyLogoSizes[size];
  const title = profile.display_title || "Alfred";
  const subtitle = profile.tagline || "Agent console";

  return (
    <div className="alfred-logo">
      {profile.has_logo && profile.logo_url ? (
        <img
          src={profile.logo_url}
          alt={`${profile.company_name || "Company"} logo`}
          className="alfred-logo-company"
          style={{ height: companyPx, width: "auto", objectFit: "contain" }}
        />
      ) : null}
      <AlfredMark size={px} className="alfred-logo-icon" />
      {!compact && (
        <div className="alfred-logo-text">
          <span className="alfred-logo-title">{title}</span>
          <span className="alfred-logo-subtitle">{subtitle}</span>
        </div>
      )}
    </div>
  );
}
