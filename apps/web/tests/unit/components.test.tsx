import type { InterviewPlan, Report } from "@intervue/types";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PlanView } from "@/components/interview/plan-view";
import { ReportView } from "@/components/reports/report-view";
import { MockNotice, ScoreRing } from "@/components/shared/primitives";

afterEach(cleanup);

const plan: InterviewPlan = {
  role_key: "aws_data_engineer",
  role_title: "AWS Data Engineer",
  experience_level: "junior",
  difficulty: "medium",
  interview_type: "full",
  duration_minutes: 45,
  rounds: [
    { id: "r1", kind: "introduction", title: "Introduction", topics: ["introduction"], minutes: 4, question_count: 1 },
    { id: "r2", kind: "technical", title: "SQL & PySpark", topics: ["sql", "pyspark"], minutes: 14, question_count: 3 },
    { id: "r3", kind: "sql", title: "SQL challenge", topics: ["sql"], minutes: 12, question_count: 1, language: "sql" },
  ],
  skill_weights: [
    { topic: "sql", label: "SQL", weight: 0.5 },
    { topic: "pyspark", label: "PySpark", weight: 0.3 },
    { topic: "introduction", label: "Communication", weight: 0.2 },
  ],
  total_questions: 5,
  rationale: ["Topics prioritised from the job requirements: SQL."],
  personalized_from_resume: true,
};

describe("PlanView", () => {
  it("shows duration, rounds and skill weights", () => {
    render(<PlanView plan={plan} />);
    expect(screen.getByText("45 min")).toBeTruthy();
    expect(screen.getByText(/SQL & PySpark/)).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText(/prioritised from the job requirements/)).toBeTruthy();
  });
});

describe("ScoreRing", () => {
  it("is accessible", () => {
    render(<ScoreRing score={72} label="Overall" />);
    expect(screen.getByRole("img", { name: "Overall: 72 out of 100" })).toBeTruthy();
  });
});

describe("MockNotice", () => {
  it("labels mock functionality only when active", () => {
    const { rerender } = render(<MockNotice show />);
    expect(screen.getByText(/mock/)).toBeTruthy();
    rerender(<MockNotice show={false} />);
    expect(screen.queryByText(/mock/)).toBeNull();
  });
});

describe("ReportView", () => {
  const report: Report = {
    overall_score: 71,
    section_scores: [{ category: "technical", score: 70 }],
    category_scores: [{ category: "technical_correctness", score: 68 }],
    category_evidence: {
      technical_correctness: [
        { source: "transcript", kind: "quote", quote: "ROW_NUMBER() OVER (PARTITION BY customer_id)", observation: "Addressed window function.", polarity: "positive" },
        { source: "transcript", kind: "absence", quote: "", observation: "Did not address tie handling.", polarity: "negative" },
      ],
    },
    role_readiness: "nearly_ready",
    readiness_label: "Nearly ready — close a few gaps",
    topic_scores: [{ topic: "sql", label: "SQL", score: 71, answered: 2 }],
    strong_areas: [],
    weak_areas: [],
    questions_missed: [],
    recommended_topics: ["tie handling"],
    practice_plan: [{ day: "Days 1-2", focus: "SQL", activities: ["Review: tie handling"] }],
    question_analysis: [{ question: "Dedup records?", topic: "SQL", kind: "primary", score: 71, summary: "Good", covered: ["window function"], missing: ["tie handling"] }],
    coding_summary: [],
    transcript_summary: "You answered 2 questions.",
    narrative: { headline: "Solid", strongest_area: "Your strongest area is SQL.", main_weakness: "No clear weakness.", summary: "", recommendations: [] },
    answered_count: 2,
    disclaimer: "AI-assisted.",
  };

  it("reveals verbatim evidence when a category is expanded", () => {
    render(
      <ReportView
        report={report}
        plan={plan}
        interview={{ id: "i", title: "t", role_key: "x", role_title: "AWS Data Engineer", interview_type: "full", duration_minutes: 45, difficulty: "medium", status: "completed", overall_score: 71, is_demo: false, organization_id: null, created_at: "2026-10-01T00:00:00Z", started_at: null, completed_at: "2026-10-01T00:30:00Z" }}
      />,
    );
    expect(screen.getByText("Your strongest area is SQL.")).toBeTruthy();
    expect(screen.queryByText(/PARTITION BY customer_id/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Technical correctness/ }));
    expect(screen.getByText(/PARTITION BY customer_id/)).toBeTruthy();
    expect(screen.getByText("Did not address tie handling.")).toBeTruthy();
  });
});
