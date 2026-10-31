# PRD — BenchOS (Consultancy Recruitment & Bench Manager)

## Original problem
Read /app/memory/product/requirements.md and build it (multi-tenant internal recruitment & bench-management platform; FastAPI + React + MongoDB; every business collection has organization_id; seed demo data; build all phases).

## User choices
TOTP MFA for Admin; SIMULATED malware scanner; Resend email MOCKED (outbox + log); light clean enterprise UI, app name "BenchOS"; continue through all phases.

## Architecture
- Backend: core.py (auth/JWT, scope, redaction, audit/timeline/notify), auth_routes.py, candidates.py (candidate service, transactional assign/transfer/unassign via version-claim lock + unique partial index on active assignment, notes/tasks/documents), pipeline.py (vendors/clients/jobs, submissions, interviews, offers, placements), admin_routes.py (users, invitations, groups/memberships, settings, saved views, audit, notifications, dashboard, reports, import/export), worker.py (bg jobs: scan, import, export, outbox), seed.py, storage.py (Emergent Object Storage).
- Frontend: React + shadcn, pages under src/pages, Layout with sidebar + mobile drawer.

## Implemented (2026-10-31)
- Invitation-only auth: password activation + Emergent Google (invited emails only), Admin TOTP MFA enforcement, brute-force lockout, refresh tokens, session revocation (session_version).
- Role + group authorization; marketing-limited scope; auditor read-only; ops-only notes; rate redaction (API, exports, audit snapshots); tenant isolation.
- Candidate wizard + quick create with live duplicate check (exact block / ops override with reason).
- Assign / transfer (typed confirm, active-offer ack) / unassign (explicit BENCH/ON_HOLD) / archive / restore (no group restore); optimistic concurrency 409.
- Guarded lifecycle; bench workspace with aging thresholds; marketing Kanban + table.
- Submissions (status history), interviews (timezones, reschedule history), offers, placements (ops, typed confirm), end placement.
- Notes, tasks, versioned documents with quarantine + simulated scan + signed short-lived download URLs; timeline; audit log.
- Dashboard, reports, CSV export (Admin/Ops/Auditor) / import (dup skip) as background jobs; notifications + MOCKED email outbox; saved views; settings thresholds.
- Seed: 2 orgs (Acme full demo, Northwind minimal).
- Tests: /app/backend/tests/test_benchos.py (32 pass).

## Round 2 (2026-10-31)
- Password reset: forgot-password (generic response, 1h single-use hashed token, link built from FRONTEND_URL, MOCKED email via outbox), reset page, sessions revoked on reset.
- Admin MFA reset (typed RESET + reason, not self) -> user re-enrolls TOTP at next login. MFA verify now rate-limited.
- Platform Organizations screen (/organizations, platform admin only): create consultancy + starter groups + invited admin with activation link.
- Emergent Google sign-in (invitation-only) verified; hardened error handling.
- Tests: 42/42 pytest pass (test_benchos.py + test_round2_auth_orgs.py).

## Backlog
- P1: Real Resend email delivery; real AV engine (e.g., ClamAV); shadcn date pickers; platform super-admin to create new tenant orgs from UI.
- P2: Saved views for other pages; bulk actions on tables; CSV export of reports; accessibility audit pass; MFA reset flow; password reset flow.
