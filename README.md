# AspireOs — Consultancy Recruitment & Bench Manager

Internal recruitment and bench-management platform for consultancies. Manages candidate intake, bench tracking, group assignment, marketing, vendor/client submissions, interviews, offers, placements, and full audit/history.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React with TypeScript and JSX |
| **Backend** | FastAPI (Python 3.11+) |
| **Database** | PostgreSQL 15+ |
| **Auth** | JWT with password and admin TOTP |
| **Storage** | S3-compatible (MinIO for local dev) |
| **Background Jobs** | Async worker process |
| **Containerization** | Docker Compose |

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  React SPA  │────▶│   FastAPI API    │────▶│  PostgreSQL  │
│  (Nginx)    │     │  (Uvicorn)       │     │              │
└─────────────┘     └──────────────────┘     └──────────────┘
                           │                        │
                    ┌──────┴──────┐          ┌──────┴──────┐
                    │   Worker    │          │    MinIO     │
                    │  (bg jobs)  │          │  (S3 store)  │
                    └─────────────┘          └─────────────┘
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for frontend dev)
- Python 3.11+ (for backend dev)

### 1. Clone & configure

```bash
git clone https://github.com/nanihustle19/axion.git
cd axion
cp backend/.env.example backend/.env
# Edit backend/.env with your values
```

### 2. Run with Docker Compose

```bash
docker compose up -d --build
# Optional demo data, after the backend is healthy
docker compose exec backend python -m app.seed
```

This starts:
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **RustFS** for local S3-compatible storage on ports 9000/9001
- **Backend API** on port 8000, after applying the Alembic migrations
- **Worker** for jobs and email delivery
- **Frontend** on port 3000

### 3. Run locally (development)

Start the local dependencies from the repository root with `docker compose up -d --wait postgres redis storage`.

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Apply the schema, then optionally load demo data
alembic upgrade head
python -m app.seed

# Start API server
uvicorn app.main:app --reload --port 8000

# Start background worker (separate terminal)
python -m app.services.worker
```

**Frontend:**
```bash
cd frontend
cp .env.example .env
yarn install --frozen-lockfile
yarn start
```

### 4. Database migrations

The initial migration expects an empty PostgreSQL database.
The active initial revision is `ed7250265465`. The archived `0001_initial_schema` revision created a different schema. If an existing database is stamped with that revision, keep it backed up and use a fresh database for this setup.

```bash
cd backend

# Generate a new migration after model changes
alembic revision --autogenerate -m "describe your change"

# Apply migrations
alembic upgrade head
```

### Account recovery and client onboarding

Set `FRONTEND_URL` to the public web app URL and configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, and credentials as needed. The worker uses implicit TLS on port 465 and STARTTLS on other ports. Without an SMTP host, messages remain queued. Run the worker alongside the API so it can deliver password reset links and invitations.

- From **Sign in**, choose **Forgot password** and follow the one-hour email link. A successful reset signs out existing sessions.
- A second admin in the same organization can reset an enrolled authenticator from **Users & Invites**. The affected admin enrolls a new authenticator at their next sign-in.
- A platform admin can choose **Organizations → New organization**, enter the consultancy and first admin details, and share the activation link. The invited admin sets their password and enrolls MFA.

Run the PostgreSQL integration suite against a freshly migrated disposable database.

```bash
cd backend
alembic upgrade head
python -m unittest discover -s tests -p postgres_integration.py
```

## Project Structure

```
axion/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, lifespan, CORS, routers
│   │   ├── config.py            # pydantic-settings configuration
│   │   ├── database.py          # SQLAlchemy async engine & session
│   │   ├── constants.py         # Roles, statuses, transitions, field lists
│   │   ├── exceptions.py        # Custom HTTP exceptions
│   │   ├── seed.py              # Database seeder with demo data
│   │   ├── models/
│   │   │   ├── base.py          # BaseModel with UUID PK, timestamps
│   │   │   ├── organization.py  # Organization
│   │   │   ├── user.py          # User, Invitation, LoginAttempt, PasswordResetToken
│   │   │   ├── group.py         # Group, Membership
│   │   │   ├── candidate.py     # Candidate, CandidateGroupAssignment
│   │   │   ├── pipeline.py      # Vendor, Client, Job, Submission, Interview, Offer, Placement
│   │   │   └── audit.py         # AuditLog, Timeline, Notification, Note, Task, Document, etc.
│   │   ├── services/
│   │   │   ├── auth_service.py  # JWT, password hashing, MFA, session, audit helpers
│   │   │   ├── authorization.py # Candidate scoping, redaction, permissions
│   │   │   ├── storage.py       # S3/MinIO object storage
│   │   │   └── worker.py        # Background job processor
│   │   └── routes/
│   │       ├── auth.py          # Login, registration, MFA, invitation, OAuth
│   │       ├── candidates.py    # Candidate CRUD, lifecycle, assignments
│   │       ├── admin.py         # Users, groups, settings, dashboard, exports
│   │       └── pipeline.py      # Vendors, clients, jobs, submissions, interviews, offers
│   ├── alembic/                 # Database migrations
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
└── docker-compose.yml
```

## Key Design Decisions

### Authorization
- **Service-layer enforcement** is the source of truth — not PostgreSQL RLS
- RLS-ready schema with `organization_id` on every table
- Group-based access: Standard users only see candidates in their groups
- Rate field redaction in API responses, exports, and audit snapshots

### One Active Group Constraint
- PostgreSQL partial unique index: `CREATE UNIQUE INDEX ON candidate_group_assignments(candidate_id) WHERE active = true`
- Transactional transfer with `SELECT FOR UPDATE` row locking
- Concurrent transfers: one wins, one gets 409 Conflict

### Document Workflow
- **Quarantine-first**: uploaded documents are `PENDING` until scanned
- Signed URLs only after scan passes
- EICAR test signature detection + extension allowlist

### Candidate Lifecycle
```
NEW → BENCH → MARKETING → SUBMITTED → INTERVIEWING → OFFERED → PLACED
 │              │                                                  │
 └→ ON_HOLD ←──┴──────────────────────────────────────────────────┘
       ↕                                                    (back to BENCH)
     BENCH
```

## User Roles

| Role | Access |
|------|--------|
| **Admin** | Full org-wide access, MFA required |
| **Operations** | Full org-wide access |
| **Employee** | Group-scoped access via memberships (Lead/Recruiter/Marketing/Viewer) |
| **Auditor** | Read-only, no OPERATIONS_ONLY content |

## Demo Credentials

After seeding, use these accounts:

| Email | Password | Role |
|-------|----------|------|
| admin@acme.test | Admin@12345 | Admin (MFA enabled) |
| ops@acme.test | Demo@12345 | Operations |
| lead@acme.test | Demo@12345 | Employee (Group Lead) |
| recruiter@acme.test | Demo@12345 | Employee (Recruiter) |
| marketing@acme.test | Demo@12345 | Employee (Marketing) |
| auditor@acme.test | Demo@12345 | Auditor |

## API Endpoints

All endpoints are prefixed with `/api/`. Authentication is via HTTP-only cookies or Bearer token.

### Auth
- `POST /api/auth/login` — Email/password login
- `POST /api/auth/mfa/verify` — MFA verification
- `POST /api/auth/google` — Google OAuth
- `POST /api/auth/invite` — Send invitation (Admin/Ops)
- `POST /api/auth/activate` — Activate account
- `POST /api/auth/refresh` — Refresh tokens
- `POST /api/auth/logout` — Logout

### Candidates
- `GET /api/candidates` — List (with pagination, filters, search)
- `POST /api/candidates` — Create
- `GET /api/candidates/{id}` — Detail
- `PATCH /api/candidates/{id}` — Update
- `POST /api/candidates/{id}/transition` — Lifecycle transition
- `POST /api/candidates/{id}/assign` — Assign to group
- `POST /api/candidates/{id}/transfer` — Transfer between groups
- `POST /api/candidates/{id}/unassign` — Remove from group

### Pipeline
- CRUD for `/api/vendors`, `/api/clients`, `/api/jobs`
- CRUD for `/api/submissions`, `/api/interviews`, `/api/offers`, `/api/placements`

### Admin
- CRUD for `/api/users`, `/api/groups`, `/api/memberships`
- `GET /api/dashboard` — Org dashboard stats
- `POST /api/exports/candidates` — Async CSV export
- `POST /api/imports/candidates` — Async CSV import

## License

Proprietary — Internal use only.

