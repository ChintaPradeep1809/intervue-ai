"use client";

import { InterviewWizard } from "@/components/interview/interview-wizard";
import { PageHeader } from "@/components/shared/primitives";

export default function NewInterviewPage() {
  return (
    <>
      <PageHeader title="New interview" description="Upload a resume, choose a target job and get a personalised plan." />
      <InterviewWizard includeProfile={false} />
    </>
  );
}
