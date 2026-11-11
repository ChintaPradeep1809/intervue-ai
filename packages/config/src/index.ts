/**
 * Product branding and public configuration. The product name is never hard-coded elsewhere:
 * set NEXT_PUBLIC_BRAND_NAME to rebrand the web app (and BRAND_NAME for the API).
 */
export const brand = {
  name: process.env.NEXT_PUBLIC_BRAND_NAME || "IntervueAI",
  tagline: "Practice. Interview. Improve.",
  description:
    "Your AI interviewer conducts realistic technical interviews tailored to your role, resume and experience.",
  supportEmail: process.env.NEXT_PUBLIC_SUPPORT_EMAIL || "support@example.com",
} as const;

export const ROLE_LABELS: Record<string, string> = {
  candidate: "Candidate",
  organization_admin: "Organization admin",
  super_admin: "Super admin",
};

export const INTERVIEW_TYPE_LABELS: Record<string, string> = {
  full: "Full interview",
  technical: "Technical",
  coding: "Coding",
  system_design: "System design",
  behavioral: "Behavioral",
};

export const ROUND_KIND_LABELS: Record<string, string> = {
  introduction: "Introduction",
  technical: "Technical",
  coding: "Live coding",
  sql: "SQL",
  system_design: "System design",
  behavioral: "Behavioral",
};
