# Requirements: Consultancy Recruitment & Bench Manager

## Core Value
Internal recruitment and bench-management platform for a consultancy to manage candidate intake, bench, group assignment, marketing, submissions, interviews, offers, placements, and full audit/history.

Web application only. Desktop-first, responsive for tablet/mobile review.

User decisions: Build on the platform stack (FastAPI + React + MongoDB; the original PostgreSQL/Supabase choice is replaced). Build everything in the plan, phase by phase. Include seed demo data. "make it as a generic app so that i can sell the product to multiple consultancies" (app is for a client; every business table/collection includes `organization_id`; design so multiple consultancies can use it as separate organizations).

## Personas & Roles
- Administrators
- Operations / HR
- Standard employees via group membership roles: Lead, Recruiter, Marketing, Viewer
- Auditors with restricted read-only access

## Features
- Invitation-only employee access with Google or password activation
- Role + group-based candidate authorization
- Candidate intake with duplicate detection and quick create
- One-active-group transactional assignment/transfer/unassignment
- Candidate lifecycle with guarded transitions
- Bench workspace and Marketing Pool
- Vendors, clients, jobs, submissions, interviews, offers, placements
- Notes, tasks, versioned documents, timeline, audit log
- Dashboards, reports, async imports/exports, notifications

Fixed decisions:
- Authorization: Application service layer is the source of truth; browser never touches business tables directly.
- Exports: Candidate exports restricted to Admin, Operations, Auditor only. Group Leads/Recruiters cannot export.
- Retention: Timeline and audit retained indefinitely.
- No downloads before malware scan passes; quarantine-first. Signed URLs only after passed scan.
- Auth: MFA enforcement for Admin; session handling.
- Background jobs for imports, exports, notifications, scanning. Notifications via outbox.
- Saved views and official threshold settings. Reporting.
- Optimistic concurrency on mutable entities. One active candidate group assignment enforced; transactional transfer service with candidate lock. `current_group_id` is projection only, never editable through generic candidate update.
- Field-level redaction for rates in APIs, exports, and audit snapshots.
- Interviews with reschedule history and timezone handling. Submissions with status history. Marketing pool table + Kanban.
- Candidate add wizard and quick create; group screens and membership flows.
- Hardening: backend integration tests, end-to-end role/transfer/lifecycle tests, performance indexing and pagination checks, accessibility review.

## Critical user flow
1. Admin invites employee
2. Employee activates via Google or password flow
3. Operations/Admin creates candidate
4. Duplicate checks run during intake
5. Candidate is assigned to a group through transactional service
6. Group works candidate through bench/marketing/submission/interview/offer/placement
7. Transfers/unassignments happen only through dedicated workflows
8. Every sensitive change creates audit + timeline records

Authorization rules:
- Admin/Operations: org-wide candidate access
- Standard users: access only via current active group membership
- Marketing users: current-group marketing-state candidates, plus currently owned BENCH/ON_HOLD candidates in their groups with limited edits
- Auditors: read-only, no OPERATIONS_ONLY content unless explicitly granted
- Pay rate visibility: Admin/Operations only
- Bill/submission/target marketing rate visibility: Admin/Operations/Group Lead/Marketing within authorized scope

## UI/UX Rules
- Dense enterprise tables, high-contrast badges, keyboard-friendly forms
- Clear permission-aware actions
- Strong confirmation dialogs for transfer, unassign, archive, placement actions
- Durable inline validation; toasts only for confirmations
- No public marketing site

## Integrations
- Auth: email/password and Google login (managed by Emergent)
- File storage: Emergent-managed uploads (private)
- Email notifications: Resend (managed by Emergent)

## Edge Cases
- Concurrent transfers: one wins, one returns 409
- Transfer with active offer: Admin/Operations only, warning + explicit acknowledgment
- Membership removal/deactivation: immediate access revoke, owner auto-clear, notify leads/ops
- Exact duplicate email/phone: hard block unless Admin/Operations override with reason
- Unassign from marketing: explicit BENCH vs ON_HOLD choice, no default
- Restore: never silently restore old group access
- Old tabs after transfer: reject by auth/version conflict

Assumptions: No native mobile app, no candidate portal, no payroll/accounting in v1.

## Seed Data
Seed/demo data (sample users, candidates, groups) as part of hardening.

## Round 2
Password Reset: Let users reset a forgotten password and let admins reset a lost authenticator
New Organizations: Add a screen so you can create a new consultancy client with its own admin in a few clicks

## Round 2 addition
Add the Emergent managed Google sign-in integration to my app.
