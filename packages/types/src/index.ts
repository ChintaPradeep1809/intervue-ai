/** Shared API and real-time event types (mirror the FastAPI response shapes). */

export type UserRole = "candidate" | "organization_admin" | "super_admin";

export interface OrgMembership {
  id: string;
  name: string;
  role: "admin" | "reviewer" | "candidate";
  kind: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_demo: boolean;
  organizations: OrgMembership[];
  onboarding_completed: boolean | null;
}

export interface PublicConfig {
  brand_name: string;
  google_oauth: boolean;
  demo_enabled: boolean;
  demo_duration_minutes: number;
  ai_is_mock: boolean;
  voice: VoiceSessionConfig;
  environment: string;
}

export interface VoiceSessionConfig {
  provider: string;
  stt: "browser" | "none";
  tts: "browser" | "server" | "none";
  language: string;
  voice_hint: string | null;
}

export interface RoleInfo {
  key: string;
  title: string;
  description: string;
  topics: string[];
  has_sql_round: boolean;
  coding_language: string;
}

export interface Catalog {
  roles: RoleInfo[];
  topics: { key: string; label: string }[];
  interview_types: string[];
  durations: number[];
  difficulties: string[];
  round_kinds: string[];
  languages: string[];
}

export type RoundKind = "introduction" | "technical" | "coding" | "sql" | "system_design" | "behavioral";

export interface PlanRound {
  id: string;
  kind: RoundKind;
  title: string;
  topics: string[];
  minutes: number;
  question_count: number;
  language?: string | null;
}

export interface InterviewPlan {
  role_key: string;
  role_title: string;
  experience_level: string;
  difficulty: string;
  interview_type: string;
  duration_minutes: number;
  rounds: PlanRound[];
  skill_weights: { topic: string; label: string; weight: number }[];
  total_questions: number;
  rationale: string[];
  personalized_from_resume: boolean;
}

export interface ResumeAnalysis {
  candidate_name: string | null;
  candidate_profile: string;
  target_role: string;
  experience_level: string;
  years_experience: number | null;
  skills: { name: string; topic: string; evidence: string }[];
  technologies: string[];
  job_requirements: string[];
  skill_gaps: string[];
  priority_topics: string[];
  interview_topics: string[];
  question_difficulty: string;
  notes: string[];
}

export type InterviewStatus = "planned" | "in_progress" | "evaluating" | "completed" | "abandoned";

export interface InterviewSummary {
  id: string;
  title: string;
  role_key: string;
  role_title: string | null;
  interview_type: string;
  duration_minutes: number;
  difficulty: string;
  status: InterviewStatus;
  overall_score: number | null;
  is_demo: boolean;
  organization_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export type Phase =
  | "INTERVIEW_SETUP"
  | "INTRODUCTION"
  | "TECHNICAL_QUESTION"
  | "FOLLOW_UP"
  | "CODING"
  | "CODE_REVIEW"
  | "SYSTEM_DESIGN"
  | "BEHAVIORAL"
  | "FINAL_EVALUATION"
  | "COMPLETED";

export interface ProblemTest {
  name: string;
  args: unknown[];
  expected: unknown;
}

export interface CodingProblemView {
  id: string;
  title: string;
  difficulty: number;
  statement: string;
  constraints?: string[];
  examples?: { input: string; output: string }[];
  function_name?: string;
  starter: Record<string, string>;
  visible_tests?: ProblemTest[];
  hidden_test_count?: number;
  schema?: {
    dataset: string;
    description: string;
    ddl: string;
    tables: { name: string; columns: string[]; row_count: number; sample: Record<string, unknown>[] }[];
  };
}

export interface LiveState {
  status: InterviewStatus;
  phase: Phase;
  next_action: "START" | "WAIT_FOR_ANSWER" | "WAIT_FOR_CODE" | "GENERATE_REPORT" | "NONE";
  rounds: { id: string; kind: RoundKind; title: string; minutes: number; status: "pending" | "active" | "completed" }[];
  round_index: number;
  current_round: PlanRound | null;
  question: { text: string; kind: string; topic: string; followup_type: string | null } | null;
  question_index: number;
  started_at: number | null;
  deadline_at: number | null;
  server_time: number;
  coding: {
    problem: CodingProblemView | null;
    language: string;
    is_sql: boolean;
    code: string;
    submitted: boolean;
    run_count: number;
  } | null;
  design_active: boolean;
  ai_is_mock: boolean;
  resumed?: boolean;
}

export interface InterviewDetail extends InterviewSummary {
  plan: InterviewPlan;
  analysis: ResumeAnalysis;
  consent: Record<string, unknown>;
  live: LiveState;
}

export type WsEventType =
  | "STATE_SYNC"
  | "INTERVIEW_STARTED"
  | "ROUND_STARTED"
  | "QUESTION_STARTED"
  | "FOLLOWUP_GENERATED"
  | "CODING_STARTED"
  | "CODE_REVIEW_STARTED"
  | "CODE_EXECUTED"
  | "ROUND_COMPLETED"
  | "AI_SPEAKING"
  | "AI_THINKING"
  | "TRANSCRIPT_PARTIAL"
  | "TRANSCRIPT_FINAL"
  | "SCREEN_SHARE_STARTED"
  | "SCREEN_SHARE_STOPPED"
  | "SCREEN_SNAPSHOT_RECEIVED"
  | "SCREEN_SHARE_DENIED"
  | "INTERVIEW_ENDING"
  | "INTERVIEW_COMPLETED"
  | "ERROR"
  | "PONG";

export interface WsEvent<P = Record<string, unknown>> {
  event_type: WsEventType;
  interview_id: string;
  timestamp: string;
  payload: P;
}

export interface SpeechSegment {
  text: string;
  kind: "greeting" | "question" | "followup" | "transition" | "ack" | "closing" | "info";
}

export interface Evidence {
  source: "transcript" | "code" | "execution" | "design";
  kind: "quote" | "absence" | "measurement";
  quote: string;
  observation: string;
  polarity: "positive" | "negative";
}

export interface CategoryScore {
  category: string;
  score: number;
}

export interface QuestionAnalysis {
  question: string;
  topic: string;
  kind: string;
  score: number;
  summary: string;
  covered: string[];
  missing: string[];
}

export interface Report {
  overall_score: number;
  section_scores: CategoryScore[];
  category_scores: CategoryScore[];
  category_evidence: Record<string, Evidence[]>;
  role_readiness: "ready" | "nearly_ready" | "developing" | "not_yet_ready" | "insufficient_data";
  readiness_label: string;
  topic_scores: { topic: string; label: string; score: number; answered: number }[];
  strong_areas: string[];
  weak_areas: string[];
  questions_missed: QuestionAnalysis[];
  recommended_topics: string[];
  practice_plan: { day: string; focus: string; activities: string[] }[];
  question_analysis: QuestionAnalysis[];
  coding_summary: { language: string; problem: string; passed: number; total: number; status: string; runtime_ms: number; runs: number }[];
  transcript_summary: string;
  narrative: { headline: string; strongest_area: string; main_weakness: string; summary: string; recommendations: string[] };
  answered_count: number;
  disclaimer: string;
}

export interface TestOutcome {
  name: string;
  passed: boolean;
  hidden: boolean;
  args?: unknown;
  expected?: unknown;
  actual?: unknown;
  error?: string | null;
  stdout?: string;
  ms?: number;
}

export interface ExecutionResult {
  kind: "run" | "submit";
  status: "passed" | "failed" | "error" | "timeout";
  passed: number;
  total: number;
  outcomes: TestOutcome[];
  error?: string | null;
  stdout?: string;
  stderr?: string;
  runtime_ms: number;
  backend?: string;
  columns?: string[];
  rows?: unknown[][];
  truncated?: boolean;
}

export interface DesignGraph {
  nodes: { id: string; kind: string; label: string }[];
  edges: { source: string; target: string; label?: string }[];
  notes: string;
}
