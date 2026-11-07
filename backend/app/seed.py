"""Database seeder — PostgreSQL/SQLAlchemy version.

Creates demo data for AspireOs: organizations, users, groups, candidates,
vendors, clients, jobs, submissions, interviews, offers, placements,
notes, tasks, notifications, and settings.

Usage:
    python -m app.seed
"""
import re
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import Base, async_session
from app.models.base import new_uuid
from app.models.organization import Organization
from app.models.user import User
from app.models.group import Group, Membership
from app.models.candidate import Candidate, CandidateGroupAssignment
from app.models.pipeline import Vendor, Client, Job, Submission, Interview, Offer, Placement
from app.models.audit import (
    AuditLog, TimelineEvent, Notification, Note, Task, Settings as OrgSettings,
)
from app.services.auth_service import hash_password

logger = logging.getLogger("benchos.seed")

DEMO_PASSWORD = "Demo@12345"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ago(days: int, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


def ahead(days: int, hour: int = 15) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    ).isoformat()


def norm_email(e: str | None) -> str | None:
    if not e:
        return None
    return e.strip().lower()


def norm_phone(p: str | None) -> str | None:
    if not p:
        return None
    return re.sub(r"\D", "", p)[-10:] or None


# ── Demo data arrays ────────────────────────────────────────────

FIRST = [
    "Aarav", "Sarah", "Priya", "Marcus", "Elena", "David", "Mei", "Carlos",
    "Fatima", "James", "Ananya", "Liam", "Olga", "Ravi", "Grace", "Tomás",
    "Nina", "Kenji", "Zoe", "Omar", "Hannah", "Vikram", "Isabel", "Noah",
    "Divya", "Lucas",
]
LAST = [
    "Patel", "Jenkins", "Sharma", "Vance", "Rostova", "Kim", "Chen", "Ortega",
    "Haddad", "Wright", "Iyer", "O'Brien", "Petrova", "Kumar", "Nguyen", "Silva",
    "Novak", "Tanaka", "Brooks", "Farouk", "Muller", "Reddy", "Garcia", "Foster",
    "Menon", "Rossi",
]
SKILLS = [
    ("Java", ["Java", "Spring Boot", "Microservices", "AWS"]),
    ("Data Engineering", ["Python", "Spark", "Airflow", "Snowflake"]),
    ("DevOps", ["Kubernetes", "Terraform", "AWS", "CI/CD"]),
    ("React", ["React", "TypeScript", "Node.js", "GraphQL"]),
    (".NET", ["C#", ".NET Core", "Azure", "SQL Server"]),
    ("Salesforce", ["Apex", "LWC", "Sales Cloud"]),
]
VISAS = ["H1B", "GC", "US Citizen", "OPT EAD", "H4 EAD", "TN"]
CITIES = [
    "Dallas, TX", "Jersey City, NJ", "Chicago, IL", "Austin, TX",
    "Atlanta, GA", "Seattle, WA", "Charlotte, NC", "Remote",
]


# ── Seed helpers ─────────────────────────────────────────────────

async def flush_seed_rows(session: AsyncSession):
    # Seed fixtures reference IDs directly, so flush parents before their dependents.
    pending = {}
    for row in session.new:
        pending.setdefault(row.__table__, []).append(row)
    for table in Base.metadata.sorted_tables:
        if rows := pending.get(table):
            await session.flush(rows)


async def seed_org(
    session: AsyncSession,
    name: str, slug: str, admin_email: str, admin_password: str,
    mfa_secret: str, full: bool = True,
):
    oid = new_uuid()
    session.add(Organization(id=oid, name=name, slug=slug, plan="Professional"))

    users: dict[str, str] = {}

    async def mk(key, email, nm, role, pw=DEMO_PASSWORD, **extra):
        uid = new_uuid()
        users[key] = uid
        session.add(User(
            id=uid, organization_id=oid, email=email, name=nm,
            role=role, status="ACTIVE", password_hash=hash_password(pw),
            auth_methods=["password"], session_version=0, **extra,
        ))

    await mk("admin", admin_email, "Alex Morgan", "ADMIN", admin_password,
             mfa_enabled=True, mfa_secret=mfa_secret, is_platform_admin=full)

    if not full:
        # Minimal org: just admin + 1 group + 3 candidates
        g = new_uuid()
        session.add(Group(id=g, organization_id=oid, name="Core Bench",
                          description="Default group", active=True))
        for i in range(3):
            session.add(Candidate(
                id=new_uuid(), organization_id=oid,
                first_name=["Ian", "Maya", "Leo"][i], last_name="Northwind",
                email=f"cand{i}@northwind-demo.test",
                email_norm=f"cand{i}@northwind-demo.test",
                phone=None, phone_norm=None, status="NEW",
                current_group_id=None, owner_id=None, primary_skill="Java",
                skills=["Java"], version=1, bench_since=None,
            ))
        await flush_seed_rows(session)
        return

    # Full org: multiple users
    await mk("ops", "ops@acme.test", "Olivia Park", "OPERATIONS")
    await mk("lead", "lead@acme.test", "Leo Fernandes", "EMPLOYEE")
    await mk("recruiter", "recruiter@acme.test", "Rita Shah", "EMPLOYEE")
    await mk("marketing", "marketing@acme.test", "Max Holloway", "EMPLOYEE")
    await mk("viewer", "viewer@acme.test", "Vera Lin", "EMPLOYEE")
    await mk("lead2", "lead2@acme.test", "Dana Brooks", "EMPLOYEE")
    await mk("auditor", "auditor@acme.test", "Arthur Quinn", "AUDITOR")

    # Pending invitation user
    session.add(User(
        id=new_uuid(), organization_id=oid, email="pending@acme.test",
        name="Paula Pending", role="EMPLOYEE", status="INVITED",
        auth_methods=[], mfa_enabled=False, session_version=0,
    ))

    await flush_seed_rows(session)

    # Groups
    groups: dict[str, str] = {}
    for key, gname, desc in [
        ("java", "Java & Cloud", "Java, Spring and cloud-native consultants"),
        ("data", "Data & Analytics", "Data engineering and BI"),
        ("devops", "DevOps & Platform", "SRE, DevOps and platform engineering"),
    ]:
        groups[key] = new_uuid()
        session.add(Group(
            id=groups[key], organization_id=oid, name=gname,
            description=desc, active=True,
        ))

    # Memberships
    for g, u, r in [
        ("java", "lead", "LEAD"), ("java", "recruiter", "RECRUITER"),
        ("java", "marketing", "MARKETING"), ("data", "marketing", "MARKETING"),
        ("data", "viewer", "VIEWER"), ("data", "lead2", "LEAD"),
        ("devops", "lead2", "LEAD"),
    ]:
        session.add(Membership(
            id=new_uuid(), organization_id=oid, group_id=groups[g],
            user_id=users[u], role=r, active=True,
        ))

    await flush_seed_rows(session)

    # Vendors
    vendors: list[str] = []
    for n, tier in [
        ("Apex Systems", "Tier 1"), ("TEKsystems", "Tier 1"),
        ("Insight Global", "Tier 2"), ("Randstad Digital", "Tier 2"),
    ]:
        vid = new_uuid()
        vendors.append(vid)
        session.add(Vendor(
            id=vid, organization_id=oid, name=n, tier=tier,
            contact_name="Account Manager",
            contact_email=f"am@{n.split()[0].lower()}.test",
            status="ACTIVE", version=1,
        ))

    # Clients
    clients: list[str] = []
    for n, ind in [
        ("Capital One", "Banking"), ("Walgreens", "Retail Health"),
        ("Verizon", "Telecom"), ("State Farm", "Insurance"),
    ]:
        cid = new_uuid()
        clients.append(cid)
        session.add(Client(
            id=cid, organization_id=oid, name=n, industry=ind,
            location=random.choice(CITIES), status="ACTIVE", version=1,
        ))

    # Jobs
    jobs: list[str] = []
    for t, sk, rate in [
        ("Senior Java Developer", ["Java", "Spring Boot"], 78),
        ("Data Engineer (Spark)", ["Spark", "Python"], 82),
        ("Platform SRE", ["Kubernetes", "Terraform"], 85),
        ("React Lead", ["React", "TypeScript"], 75),
        ("Java Microservices Architect", ["Java", "AWS"], 95),
        ("Snowflake Data Architect", ["Snowflake"], 90),
    ]:
        jid = new_uuid()
        jobs.append(jid)
        session.add(Job(
            id=jid, organization_id=oid, title=t,
            client_id=random.choice(clients), vendor_id=random.choice(vendors),
            skills=sk, rate=rate, location=random.choice(CITIES),
            work_mode=random.choice(["Remote", "Hybrid", "Onsite"]),
            openings=1, status="OPEN", version=1,
        ))

    await flush_seed_rows(session)

    # ── Candidates ───────────────────────────────────────────────
    random.seed(7)
    plan = [
        ("java", "MARKETING"), ("java", "SUBMITTED"), ("java", "INTERVIEWING"),
        ("java", "OFFERED"), ("java", "BENCH"), ("java", "BENCH"),
        ("java", "PLACED"), ("java", "ON_HOLD"),
        ("data", "MARKETING"), ("data", "SUBMITTED"), ("data", "BENCH"),
        ("data", "INTERVIEWING"), ("data", "BENCH"),
        ("devops", "MARKETING"), ("devops", "BENCH"), ("devops", "PLACED"),
        ("devops", "SUBMITTED"),
        (None, "NEW"), (None, "NEW"), (None, "BENCH"), (None, "ARCHIVED"),
        ("data", "MARKETING"), ("java", "MARKETING"), ("devops", "ON_HOLD"),
    ]

    for i, (gk, st) in enumerate(plan):
        cid = new_uuid()
        fn, ln = FIRST[i], LAST[i]
        skill = (
            SKILLS[0] if gk == "java" else
            SKILLS[1] if gk == "data" else
            SKILLS[2] if gk == "devops" else
            random.choice(SKILLS)
        )
        gid = groups.get(gk) if gk else None
        owner = (
            users["recruiter"] if gk == "java" and i % 2 == 0 else
            users["marketing"] if gk == "java" and st == "BENCH" else
            None
        )
        bench_days = random.randint(2, 45)
        pay = random.randint(45, 70)
        email = f"{fn.lower()}.{ln.lower().replace(chr(39), '')}@mail.test"

        c_kwargs = dict(
            id=cid, organization_id=oid, first_name=fn, last_name=ln,
            email=email, phone=f"(555) 01{i:02d}-{1000 + i * 37}",
            email_norm=norm_email(email),
            phone_norm=norm_phone(f"(555) 01{i:02d}-{1000 + i * 37}"),
            location=random.choice(CITIES),
            primary_skill=skill[0], skills=skill[1],
            experience_years=random.randint(4, 16),
            visa_status=random.choice(VISAS),
            work_authorization="Authorized",
            source=random.choice(["Referral", "LinkedIn", "Dice", "Internal"]),
            pay_rate=pay, bill_rate=pay + random.randint(15, 30),
            target_rate=pay + random.randint(18, 28),
            availability_date=ahead(random.randint(0, 21))[:10],
            summary=f"{skill[0]} consultant with strong delivery background.",
            relocation=(i % 3 == 0), timezone="America/Chicago",
            status=st, current_group_id=gid, owner_id=owner,
            version=1, created_by=users["ops"],
            bench_since=ago(bench_days) if st in ("BENCH", "ON_HOLD") else None,
        )
        if st == "ARCHIVED":
            c_kwargs["prior_status"] = "BENCH"

        session.add(Candidate(**c_kwargs))

        # Timeline: created
        session.add(TimelineEvent(
            id=new_uuid(), organization_id=oid, candidate_id=cid,
            event="CREATED", detail="Candidate created (seed)",
            actor_name="Olivia Park", meta={},
        ))

        # Audit log: created
        session.add(AuditLog(
            id=new_uuid(), organization_id=oid, actor_id=users["ops"],
            actor_name="Olivia Park", action="CANDIDATE_CREATED",
            entity_type="candidate", entity_id=cid,
            before=None,
            after={"first_name": fn, "last_name": ln, "pay_rate": pay},
        ))

        # Group assignment
        if gid:
            session.add(CandidateGroupAssignment(
                id=new_uuid(), organization_id=oid, candidate_id=cid,
                group_id=gid, active=True, started_at=ago(55 - i),
                started_by=users["ops"],
            ))
            session.add(TimelineEvent(
                id=new_uuid(), organization_id=oid, candidate_id=cid,
                event="ASSIGNED", detail="Assigned to group (seed)",
                actor_name="Olivia Park", meta={},
            ))

        # Pipeline data for downstream statuses
        if st in ("SUBMITTED", "INTERVIEWING", "OFFERED", "PLACED"):
            jid = jobs[i % len(jobs)]
            sid = new_uuid()
            sub_status = {
                "SUBMITTED": "CLIENT_REVIEW", "INTERVIEWING": "INTERVIEW",
                "OFFERED": "OFFER", "PLACED": "PLACED",
            }[st]
            session.add(Submission(
                id=sid, organization_id=oid, candidate_id=cid, job_id=jid,
                group_id=gid, submission_rate=pay + random.randint(15, 30),
                status=sub_status, version=1,
                status_history=[
                    {"status": "SUBMITTED", "at": ago(10 - i % 7), "by": "Rita Shah"},
                    {"status": sub_status, "at": ago(5 - i % 4), "by": "Rita Shah"},
                ],
                submitted_by=users["recruiter"],
                submitted_by_name="Rita Shah",
            ))

            if st in ("INTERVIEWING", "OFFERED", "PLACED"):
                session.add(Interview(
                    id=new_uuid(), organization_id=oid, candidate_id=cid,
                    submission_id=sid, job_id=jid, group_id=gid,
                    scheduled_at=ahead(1 + i % 5) if st == "INTERVIEWING" else ago(6),
                    timezone="America/New_York", duration_minutes=60,
                    mode="VIDEO", round="Technical", interviewer="Hiring Manager",
                    status="SCHEDULED" if st == "INTERVIEWING" else "COMPLETED",
                    version=1,
                    reschedule_history=(
                        [{
                            "from": ahead(0), "from_tz": "America/Chicago",
                            "to": ahead(1 + i % 5), "to_tz": "America/New_York",
                            "reason": "Client conflict", "by": "Rita Shah", "at": ago(1),
                        }] if st == "INTERVIEWING" else []
                    ),
                    created_by=users["recruiter"],
                ))

            if st in ("OFFERED", "PLACED"):
                ofid = new_uuid()
                session.add(Offer(
                    id=ofid, organization_id=oid, candidate_id=cid,
                    submission_id=sid, job_id=jid, group_id=gid,
                    bill_rate=pay + random.randint(15, 30), pay_rate=pay,
                    start_date=ahead(14)[:10],
                    status="EXTENDED" if st == "OFFERED" else "ACCEPTED",
                    version=1, created_by=users["lead"],
                ))
                if st == "PLACED":
                    session.add(Placement(
                        id=new_uuid(), organization_id=oid, candidate_id=cid,
                        offer_id=ofid, job_id=jid, group_id=gid,
                        bill_rate=pay + random.randint(15, 30), pay_rate=pay,
                        start_date=ago(3)[:10], end_date=ahead(180)[:10],
                        status="ACTIVE", version=1, created_by=users["ops"],
                    ))

        # Notes
        if i % 3 == 0:
            session.add(Note(
                id=new_uuid(), organization_id=oid, candidate_id=cid,
                body="Strong communication; prefers remote roles.",
                visibility="STANDARD",
                author_id=users["recruiter"], author_name="Rita Shah",
            ))
        if i % 4 == 0:
            session.add(Note(
                id=new_uuid(), organization_id=oid, candidate_id=cid,
                body="Payroll: confirm W2 vs C2C before offer.",
                visibility="OPERATIONS_ONLY",
                author_id=users["ops"], author_name="Olivia Park",
            ))

        # Tasks
        if i % 5 == 0:
            session.add(Task(
                id=new_uuid(), organization_id=oid, candidate_id=cid,
                title=f"Follow up with {fn} on availability",
                assignee_id=users["recruiter"] if gk == "java" else users["ops"],
                due_date=ahead(i % 6)[:10],
                priority=random.choice(["HIGH", "MEDIUM", "LOW"]),
                status="OPEN", created_by=users["lead"],
            ))

    # Welcome notification
    session.add(Notification(
        id=new_uuid(), organization_id=oid, user_id=users["admin"],
        title="Welcome to AspireOs",
        body="Demo data has been loaded.", read=False,
    ))

    # Org settings
    session.add(OrgSettings(
        id=new_uuid(), organization_id=oid,
        bench_aging_warning_days=14, bench_aging_critical_days=30,
        weekly_submission_target=5, interview_default_timezone="America/New_York",
    ))

    await flush_seed_rows(session)


async def seed():
    """Load demo data into an already migrated database."""
    settings = get_settings()

    async with async_session() as session:
        # Set platform admin flag
        admin_email = settings.ADMIN_EMAIL.strip().lower()
        if admin_email:
            result = await session.execute(
                select(User).where(User.email == admin_email)
            )
            admin_user = result.scalar_one_or_none()
            if admin_user and not admin_user.is_platform_admin:
                admin_user.is_platform_admin = True

        # Check if already seeded
        result = await session.execute(select(Organization).limit(1))
        if result.scalar_one_or_none():
            logger.info("Database already seeded — skipping")
            await session.commit()
            return

        logger.info("Seeding demo data...")

        await seed_org(
            session,
            "Acme Consulting", "acme",
            admin_email or "admin@acme.test",
            settings.ADMIN_PASSWORD or "Admin@12345",
            settings.ADMIN_MFA_SECRET or "JBSWY3DPEHPK3PXP",
        )
        await seed_org(
            session,
            "Northwind Talent", "northwind",
            "admin@northwind.test",
            DEMO_PASSWORD,
            settings.ADMIN_MFA_SECRET or "JBSWY3DPEHPK3PXP",
            full=False,
        )

        await session.commit()
        logger.info("Seed data loaded successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())

