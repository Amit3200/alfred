import type { PublicBranding } from "./api/client";

/** Small fixed credit shown in the admin console footer. */
export const ALFRED_CREDIT = {
  label: "Crafted by @amit3200",
  href: "https://github.com/amit3200",
} as const;

export function defaultPublicBranding(): PublicBranding {
  return {
    company_name: "",
    tagline: "Agent console",
    display_title: "Alfred",
    setup_completed: false,
    has_logo: false,
    logo_url: "",
  };
}

export function brandingFromConfig(config: {
  branding?: {
    company_name?: string;
    tagline?: string;
    setup_completed?: boolean;
    logo_ext?: string;
  };
}): PublicBranding {
  const company = config.branding?.company_name?.trim() || "";
  const tagline = config.branding?.tagline?.trim() || "Agent console";
  return {
    company_name: company,
    tagline,
    display_title: company ? `Alfred × ${company}` : "Alfred",
    setup_completed: config.branding?.setup_completed ?? false,
    has_logo: Boolean(config.branding?.logo_ext),
    logo_url: config.branding?.logo_ext ? `/api/branding/logo?v=0` : "",
  };
}
