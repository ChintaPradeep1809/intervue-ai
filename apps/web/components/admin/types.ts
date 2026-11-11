export interface CandidateRow {
  interview_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  role: string;
  role_key: string;
  interview: string;
  score: number | null;
  status: string;
  review_status: string;
  date: string;
}
