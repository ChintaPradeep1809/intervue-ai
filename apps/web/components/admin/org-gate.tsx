"use client";

import { Building2 } from "lucide-react";

import { EmptyState, LinkButton } from "@/components/shared/primitives";
import { useSession } from "@/lib/session";

/** Renders children only for organisation admins/reviewers; otherwise points to org setup. */
export function OrgGate({ children }: { children: React.ReactNode }) {
  const { user } = useSession();
  const hasOrg = !!user?.organizations.some((o) => o.role === "admin" || o.role === "reviewer");
  if (!hasOrg)
    return (
      <EmptyState
        icon={Building2}
        title="Set up your organization"
        description="Create an organization to build interview templates, invite candidates and see cohort results."
        action={<LinkButton href="/organization/settings?setup=1">Create organization</LinkButton>}
      />
    );
  return <>{children}</>;
}
