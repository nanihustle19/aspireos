/**
 * BenchOS — Shared TypeScript type definitions.
 *
 * These types match the backend SQLAlchemy models and API responses.
 */

// ── Organization ────────────────────────────────────────────────

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  created_at: string;
}

// ── Users ───────────────────────────────────────────────────────

export type OrgRole = "ADMIN" | "OPERATIONS" | "EMPLOYEE" | "AUDITOR";
export type UserStatus = "INVITED" | "ACTIVE" | "DEACTIVATED";
export type GroupRole = "LEAD" | "RECRUITER" | "MARKETING" | "VIEWER";

export interface User {
  id: string;
  organization_id: string;
  email: string;
  name: string;
  role: OrgRole;
  status: UserStatus;
  mfa_enabled: boolean;
  session_version: number;
  picture?: string | null;
  is_platform_admin: boolean;
  can_view_ops_only: boolean;
  auth_methods: string[];
  last_login_at?: string | null;
  created_at: string;
}

export interface Invitation {
  id: string;
  organization_id: string;
  user_id: string;
  email: string;
  name: string;
  role: OrgRole;
  token: string;
  status: "PENDING" | "ACCEPTED" | "REVOKED";
  invited_by: string;
  invited_by_name: string;
  expires_at: string;
  accepted_at?: string | null;
  created_at: string;
}

// ── Groups ──────────────────────────────────────────────────────

export interface Group {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  active: boolean;
  created_at: string;
}

export interface Membership {
  id: string;
  organization_id: string;
  group_id: string;
  user_id: string;
  role: GroupRole;
  active: boolean;
  created_at: string;
  ended_at?: string | null;
  ended_by?: string | null;
  end_reason?: string | null;
}

export interface UserGroup extends Group {
  role: GroupRole;
}

// ── Candidates ──────────────────────────────────────────────────

export type CandidateStatus =
  | "NEW"
  | "BENCH"
  | "MARKETING"
  | "SUBMITTED"
  | "INTERVIEWING"
  | "OFFERED"
  | "PLACED"
  | "ON_HOLD"
  | "ARCHIVED";

export interface Candidate {
  id: string;
  organization_id: string;
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  primary_skill?: string | null;
  skills: string[];
  experience_years?: number | null;
  visa_status?: string | null;
  work_authorization?: string | null;
  availability_date?: string | null;
  source?: string | null;
  linkedin_url?: string | null;
  pay_rate?: number | null;
  bill_rate?: number | null;
  target_rate?: number | null;
  summary?: string | null;
  relocation?: boolean | null;
  timezone?: string | null;
  status: CandidateStatus;
  prior_status?: CandidateStatus | null;
  current_group_id?: string | null;
  owner_id?: string | null;
  version: number;
  bench_since?: string | null;
  created_at: string;
  updated_at?: string | null;
  created_by?: string | null;
  /** Fields that were redacted for this user */
  _redacted?: string[];
}

export interface CandidateGroupAssignment {
  id: string;
  organization_id: string;
  candidate_id: string;
  group_id: string;
  active: boolean;
  started_at: string;
  started_by: string;
  reason?: string | null;
  ended_at?: string | null;
  ended_by?: string | null;
  end_reason?: string | null;
}

// ── Pipeline ────────────────────────────────────────────────────

export interface Vendor {
  id: string;
  organization_id: string;
  name: string;
  contact_name?: string | null;
  contact_email?: string | null;
  phone?: string | null;
  tier?: string | null;
  notes?: string | null;
  status: string;
  version: number;
  created_at: string;
}

export interface Client {
  id: string;
  organization_id: string;
  name: string;
  industry?: string | null;
  location?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  notes?: string | null;
  status: string;
  version: number;
  created_at: string;
}

export interface Job {
  id: string;
  organization_id: string;
  title: string;
  client_id?: string | null;
  vendor_id?: string | null;
  location?: string | null;
  work_mode?: string | null;
  rate?: number | null;
  skills: string[];
  description?: string | null;
  openings?: number | null;
  status: string;
  version: number;
  created_at: string;
}

export type SubmissionStatus =
  | "SUBMITTED"
  | "CLIENT_REVIEW"
  | "INTERVIEW"
  | "OFFER"
  | "REJECTED"
  | "WITHDRAWN"
  | "PLACED";

export interface StatusHistoryEntry {
  status: string;
  at: string;
  by: string;
}

export interface Submission {
  id: string;
  organization_id: string;
  candidate_id: string;
  job_id: string;
  client_id?: string | null;
  vendor_id?: string | null;
  group_id?: string | null;
  submission_rate?: number | null;
  notes?: string | null;
  status: SubmissionStatus;
  status_history: StatusHistoryEntry[];
  submitted_by?: string | null;
  submitted_by_name?: string | null;
  version: number;
  created_at: string;
}

export interface RescheduleEntry {
  from: string;
  from_tz: string;
  to: string;
  to_tz: string;
  reason: string;
  by: string;
  at: string;
}

export interface Interview {
  id: string;
  organization_id: string;
  candidate_id: string;
  submission_id: string;
  job_id: string;
  group_id?: string | null;
  scheduled_at: string;
  timezone: string;
  duration_minutes: number;
  mode: string;
  round: string;
  interviewer?: string | null;
  status: string;
  reschedule_history: RescheduleEntry[];
  feedback?: string | null;
  version: number;
  created_at: string;
}

export interface Offer {
  id: string;
  organization_id: string;
  candidate_id: string;
  submission_id: string;
  job_id: string;
  group_id?: string | null;
  bill_rate?: number | null;
  pay_rate?: number | null;
  start_date?: string | null;
  notes?: string | null;
  status: string;
  version: number;
  created_at: string;
}

export interface Placement {
  id: string;
  organization_id: string;
  candidate_id: string;
  offer_id: string;
  job_id: string;
  group_id?: string | null;
  bill_rate?: number | null;
  pay_rate?: number | null;
  start_date: string;
  end_date?: string | null;
  status: string;
  ended_at?: string | null;
  end_reason?: string | null;
  version: number;
  created_at: string;
}

// ── Audit & Activity ────────────────────────────────────────────

export interface AuditLogEntry {
  id: string;
  organization_id: string;
  actor_id: string;
  actor_name?: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  candidate_id?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string | null;
  created_at: string;
}

export interface TimelineEvent {
  id: string;
  organization_id: string;
  candidate_id: string;
  event: string;
  detail: string;
  meta?: Record<string, unknown> | null;
  actor_id?: string | null;
  actor_name?: string | null;
  created_at: string;
}

export interface Notification {
  id: string;
  organization_id: string;
  user_id: string;
  title: string;
  body: string;
  link?: string | null;
  read: boolean;
  created_at: string;
}

export interface Note {
  id: string;
  organization_id: string;
  candidate_id: string;
  body: string;
  visibility: "STANDARD" | "OPERATIONS_ONLY";
  author_id: string;
  author_name: string;
  created_at: string;
}

export interface Task {
  id: string;
  organization_id: string;
  candidate_id?: string | null;
  title: string;
  assignee_id?: string | null;
  due_date?: string | null;
  priority: "HIGH" | "MEDIUM" | "LOW";
  status: "OPEN" | "DONE" | "CANCELLED";
  created_by: string;
  created_at: string;
}

export interface Document {
  id: string;
  organization_id: string;
  candidate_id: string;
  doc_type: string;
  version: number;
  original_filename: string;
  content_type?: string | null;
  size: number;
  storage_path: string;
  scan_status: "PENDING" | "PASSED" | "FAILED";
  scan_engine: string;
  scan_reason?: string | null;
  scanned_at?: string | null;
  is_deleted: boolean;
  uploaded_by: string;
  uploaded_by_name: string;
  created_at: string;
}

export interface BackgroundJob {
  id: string;
  organization_id: string;
  type: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  payload?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  result_csv?: string | null;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_by: string;
  created_by_name?: string | null;
  created_at: string;
}

export interface SavedView {
  id: string;
  name: string;
  page: string;
  filters: Record<string, unknown>;
}

export interface OrgSettings {
  bench_aging_warning_days: number;
  bench_aging_critical_days: number;
  weekly_submission_target: number;
  interview_default_timezone: string;
}

// ── API Responses ───────────────────────────────────────────────

export interface AuthSession {
  user: User;
  organization: Organization;
  groups: UserGroup[];
  access_token: string;
  refresh_token: string;
}

export interface MfaRequiredResponse {
  mfa_required: true;
  mfa_token: string;
}

export interface MfaSetupResponse {
  mfa_setup_required: true;
  mfa_token: string;
  secret: string;
  otpauth_uri: string;
}

export type LoginResponse = AuthSession | MfaRequiredResponse | MfaSetupResponse;

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DuplicateWarning {
  id: string;
  first_name: string;
  last_name: string;
  match: string;
}

export interface DashboardStats {
  total_candidates: number;
  by_status: Record<CandidateStatus, number>;
  bench_candidates: number;
  aging_warning: number;
  aging_critical: number;
  active_placements: number;
  pending_offers: number;
  this_week_submissions: number;
  submission_target: number;
  open_tasks: number;
  unread_notifications: number;
}

export interface ReportData {
  type: string;
  data: Record<string, unknown>[];
}

// ── Form/Input Types ────────────────────────────────────────────

export interface CandidateCreateInput {
  first_name: string;
  last_name: string;
  email?: string;
  phone?: string;
  location?: string;
  primary_skill?: string;
  skills?: string[];
  experience_years?: number;
  visa_status?: string;
  work_authorization?: string;
  availability_date?: string;
  source?: string;
  linkedin_url?: string;
  pay_rate?: number;
  bill_rate?: number;
  target_rate?: number;
  summary?: string;
  relocation?: boolean;
  timezone?: string;
}

export interface CandidateUpdateInput extends Partial<CandidateCreateInput> {
  version: number;
}

export interface TransitionInput {
  target_status: CandidateStatus;
  reason?: string;
  new_status_after_unassign?: "BENCH" | "ON_HOLD";
}

export interface AssignInput {
  group_id: string;
  reason?: string;
}

export interface TransferInput {
  target_group_id: string;
  reason?: string;
  acknowledge_active_offer?: boolean;
}

export interface InviteInput {
  email: string;
  name: string;
  role: OrgRole;
}

