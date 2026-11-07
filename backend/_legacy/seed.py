import os
import random
from datetime import datetime, timezone, timedelta

from core import db, hash_password, new_id, now, logger
from candidates import norm_email, norm_phone

DEMO_PASSWORD = "Demo@12345"


def ago(days, hours=0):
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


def ahead(days, hour=15):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.candidates.create_index("id", unique=True)
    await db.candidates.create_index([("organization_id", 1), ("status", 1)])
    await db.candidates.create_index([("organization_id", 1), ("current_group_id", 1)])
    await db.candidates.create_index([("organization_id", 1), ("email_norm", 1)])
    await db.candidates.create_index([("organization_id", 1), ("phone_norm", 1)])
    await db.candidates.create_index([("organization_id", 1), ("updated_at", -1)])
    await db.assignments.create_index("candidate_id", unique=True, partialFilterExpression={"active": True})
    await db.memberships.create_index([("user_id", 1), ("active", 1)])
    await db.memberships.create_index([("group_id", 1), ("active", 1)])
    await db.timeline.create_index([("candidate_id", 1), ("created_at", -1)])
    await db.audit_logs.create_index([("organization_id", 1), ("created_at", -1)])
    await db.audit_logs.create_index("entity_id")
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.bg_jobs.create_index([("status", 1), ("created_at", 1)])
    await db.outbox.create_index("status")
    await db.login_attempts.create_index("identifier")
    await db.organizations.create_index("slug", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.password_reset_tokens.create_index("token_hash")
    for c in ("submissions", "interviews", "offers", "placements"):
        await db[c].create_index([("organization_id", 1), ("group_id", 1)])
        await db[c].create_index("candidate_id")


FIRST = ["Aarav", "Sarah", "Priya", "Marcus", "Elena", "David", "Mei", "Carlos", "Fatima", "James", "Ananya", "Liam", "Olga", "Ravi",
         "Grace", "Tomás", "Nina", "Kenji", "Zoe", "Omar", "Hannah", "Vikram", "Isabel", "Noah", "Divya", "Lucas"]
LAST = ["Patel", "Jenkins", "Sharma", "Vance", "Rostova", "Kim", "Chen", "Ortega", "Haddad", "Wright", "Iyer", "O'Brien", "Petrova", "Kumar",
        "Nguyen", "Silva", "Novak", "Tanaka", "Brooks", "Farouk", "Muller", "Reddy", "Garcia", "Foster", "Menon", "Rossi"]
SKILLS = [("Java", ["Java", "Spring Boot", "Microservices", "AWS"]), ("Data Engineering", ["Python", "Spark", "Airflow", "Snowflake"]),
          ("DevOps", ["Kubernetes", "Terraform", "AWS", "CI/CD"]), ("React", ["React", "TypeScript", "Node.js", "GraphQL"]),
          (".NET", ["C#", ".NET Core", "Azure", "SQL Server"]), ("Salesforce", ["Apex", "LWC", "Sales Cloud"])]
VISAS = ["H1B", "GC", "US Citizen", "OPT EAD", "H4 EAD", "TN"]
CITIES = ["Dallas, TX", "Jersey City, NJ", "Chicago, IL", "Austin, TX", "Atlanta, GA", "Seattle, WA", "Charlotte, NC", "Remote"]


async def seed_org(name, slug, admin_email, admin_password, mfa_secret, full=True):
    oid = new_id()
    await db.organizations.insert_one({"id": oid, "name": name, "slug": slug, "plan": "Professional", "created_at": now()})
    users = {}

    async def mk(key, email, nm, role, pw=DEMO_PASSWORD, **extra):
        uid = new_id()
        users[key] = uid
        await db.users.insert_one({"id": uid, "organization_id": oid, "email": email, "name": nm, "role": role, "status": "ACTIVE",
                                   "password_hash": hash_password(pw), "auth_methods": ["password"], "mfa_enabled": False,
                                   "session_version": 0, "created_at": ago(120)} | extra)

    await mk("admin", admin_email, "Alex Morgan", "ADMIN", admin_password, mfa_enabled=True, mfa_secret=mfa_secret)
    if not full:
        g = new_id()
        await db.groups.insert_one({"id": g, "organization_id": oid, "name": "Core Bench", "description": "Default group", "active": True, "created_at": ago(90)})
        for i in range(3):
            await db.candidates.insert_one({"id": new_id(), "organization_id": oid, "first_name": ["Ian", "Maya", "Leo"][i], "last_name": "Northwind",
                                            "email": f"cand{i}@northwind-demo.test", "email_norm": f"cand{i}@northwind-demo.test", "phone": None, "phone_norm": None,
                                            "status": "NEW", "current_group_id": None, "owner_id": None, "primary_skill": "Java", "skills": ["Java"],
                                            "version": 1, "created_at": ago(5), "updated_at": ago(5), "bench_since": None})
        return
    await mk("ops", "ops@acme.test", "Olivia Park", "OPERATIONS")
    await mk("lead", "lead@acme.test", "Leo Fernandes", "EMPLOYEE")
    await mk("recruiter", "recruiter@acme.test", "Rita Shah", "EMPLOYEE")
    await mk("marketing", "marketing@acme.test", "Max Holloway", "EMPLOYEE")
    await mk("viewer", "viewer@acme.test", "Vera Lin", "EMPLOYEE")
    await mk("lead2", "lead2@acme.test", "Dana Brooks", "EMPLOYEE")
    await mk("auditor", "auditor@acme.test", "Arthur Quinn", "AUDITOR")
    await db.users.insert_one({"id": new_id(), "organization_id": oid, "email": "pending@acme.test", "name": "Paula Pending", "role": "EMPLOYEE",
                               "status": "INVITED", "auth_methods": [], "mfa_enabled": False, "session_version": 0, "created_at": ago(1)})

    groups = {}
    for key, gname, desc in [("java", "Java & Cloud", "Java, Spring and cloud-native consultants"), ("data", "Data & Analytics", "Data engineering and BI"),
                             ("devops", "DevOps & Platform", "SRE, DevOps and platform engineering")]:
        groups[key] = new_id()
        await db.groups.insert_one({"id": groups[key], "organization_id": oid, "name": gname, "description": desc, "active": True, "created_at": ago(100)})
    for g, u, r in [("java", "lead", "LEAD"), ("java", "recruiter", "RECRUITER"), ("java", "marketing", "MARKETING"), ("data", "marketing", "MARKETING"),
                    ("data", "viewer", "VIEWER"), ("data", "lead2", "LEAD"), ("devops", "lead2", "LEAD")]:
        await db.memberships.insert_one({"id": new_id(), "organization_id": oid, "group_id": groups[g], "user_id": users[u], "role": r, "active": True, "created_at": ago(90)})

    vendors, clients, jobs = [], [], []
    for n, tier in [("Apex Systems", "Tier 1"), ("TEKsystems", "Tier 1"), ("Insight Global", "Tier 2"), ("Randstad Digital", "Tier 2")]:
        vid = new_id(); vendors.append(vid)
        await db.vendors.insert_one({"id": vid, "organization_id": oid, "name": n, "tier": tier, "contact_name": "Account Manager", "contact_email": f"am@{n.split()[0].lower()}.test", "status": "ACTIVE", "version": 1, "created_at": ago(80)})
    for n, ind in [("Capital One", "Banking"), ("Walgreens", "Retail Health"), ("Verizon", "Telecom"), ("State Farm", "Insurance")]:
        cid = new_id(); clients.append(cid)
        await db.clients.insert_one({"id": cid, "organization_id": oid, "name": n, "industry": ind, "location": random.choice(CITIES), "status": "ACTIVE", "version": 1, "created_at": ago(80)})
    for t, sk, rate in [("Senior Java Developer", ["Java", "Spring Boot"], 78), ("Data Engineer (Spark)", ["Spark", "Python"], 82), ("Platform SRE", ["Kubernetes", "Terraform"], 85),
                        ("React Lead", ["React", "TypeScript"], 75), ("Java Microservices Architect", ["Java", "AWS"], 95), ("Snowflake Data Architect", ["Snowflake"], 90)]:
        jid = new_id(); jobs.append(jid)
        await db.jobs.insert_one({"id": jid, "organization_id": oid, "title": t, "client_id": random.choice(clients), "vendor_id": random.choice(vendors), "skills": sk,
                                  "rate": rate, "location": random.choice(CITIES), "work_mode": random.choice(["Remote", "Hybrid", "Onsite"]), "openings": 1, "status": "OPEN", "version": 1, "created_at": ago(30)})

    random.seed(7)
    plan = [("java", "MARKETING"), ("java", "SUBMITTED"), ("java", "INTERVIEWING"), ("java", "OFFERED"), ("java", "BENCH"), ("java", "BENCH"),
            ("java", "PLACED"), ("java", "ON_HOLD"), ("data", "MARKETING"), ("data", "SUBMITTED"), ("data", "BENCH"), ("data", "INTERVIEWING"),
            ("data", "BENCH"), ("devops", "MARKETING"), ("devops", "BENCH"), ("devops", "PLACED"), ("devops", "SUBMITTED"), (None, "NEW"),
            (None, "NEW"), (None, "BENCH"), (None, "ARCHIVED"), ("data", "MARKETING"), ("java", "MARKETING"), ("devops", "ON_HOLD")]
    admin_u = {"id": users["admin"], "name": "Alex Morgan"}
    for i, (gk, st) in enumerate(plan):
        cid = new_id()
        fn, ln = FIRST[i], LAST[i]
        skill = SKILLS[0] if gk == "java" else SKILLS[1] if gk == "data" else SKILLS[2] if gk == "devops" else random.choice(SKILLS)
        gid = groups.get(gk)
        owner = users["recruiter"] if gk == "java" and i % 2 == 0 else users["marketing"] if gk == "java" and st == "BENCH" else None
        bench_days = random.randint(2, 45)
        pay = random.randint(45, 70)
        c = {"id": cid, "organization_id": oid, "first_name": fn, "last_name": ln, "email": f"{fn.lower()}.{ln.lower().replace(chr(39), '')}@mail.test",
             "phone": f"(555) 01{i:02d}-{1000 + i * 37}", "location": random.choice(CITIES), "primary_skill": skill[0], "skills": skill[1],
             "experience_years": random.randint(4, 16), "visa_status": random.choice(VISAS), "work_authorization": "Authorized", "source": random.choice(["Referral", "LinkedIn", "Dice", "Internal"]),
             "pay_rate": pay, "bill_rate": pay + random.randint(15, 30), "target_rate": pay + random.randint(18, 28), "availability_date": ahead(random.randint(0, 21))[:10],
             "summary": f"{skill[0]} consultant with strong delivery background.", "relocation": i % 3 == 0, "timezone": "America/Chicago",
             "status": st, "current_group_id": gid, "owner_id": owner, "version": 1, "created_at": ago(60 - i), "updated_at": ago(i % 9),
             "created_by": users["ops"], "bench_since": ago(bench_days) if st in ("BENCH", "ON_HOLD") else None}
        if st == "ARCHIVED":
            c["prior_status"] = "BENCH"
        c["email_norm"], c["phone_norm"] = norm_email(c["email"]), norm_phone(c["phone"])
        await db.candidates.insert_one(c)
        await db.timeline.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "event": "CREATED", "detail": "Candidate created (seed)", "actor_name": "Olivia Park", "created_at": c["created_at"], "meta": {}})
        await db.audit_logs.insert_one({"id": new_id(), "organization_id": oid, "actor_id": users["ops"], "actor_name": "Olivia Park", "action": "CANDIDATE_CREATED",
                                        "entity_type": "candidate", "entity_id": cid, "before": None, "after": {"first_name": fn, "last_name": ln, "pay_rate": pay}, "created_at": c["created_at"]})
        if gid:
            await db.assignments.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "group_id": gid, "active": True, "started_at": ago(55 - i), "started_by": users["ops"]})
            await db.timeline.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "event": "ASSIGNED", "detail": "Assigned to group (seed)", "actor_name": "Olivia Park", "created_at": ago(55 - i), "meta": {}})
        if st in ("SUBMITTED", "INTERVIEWING", "OFFERED", "PLACED"):
            jid = jobs[i % len(jobs)]
            sid = new_id()
            sub_status = {"SUBMITTED": "CLIENT_REVIEW", "INTERVIEWING": "INTERVIEW", "OFFERED": "OFFER", "PLACED": "PLACED"}[st]
            await db.submissions.insert_one({"id": sid, "organization_id": oid, "candidate_id": cid, "job_id": jid, "group_id": gid, "submission_rate": c["bill_rate"],
                                             "status": sub_status, "version": 1, "status_history": [{"status": "SUBMITTED", "at": ago(10 - i % 7), "by": "Rita Shah"}, {"status": sub_status, "at": ago(5 - i % 4), "by": "Rita Shah"}],
                                             "submitted_by": users["recruiter"], "submitted_by_name": "Rita Shah", "created_at": ago(i % 12)})
            if st in ("INTERVIEWING", "OFFERED", "PLACED"):
                await db.interviews.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "submission_id": sid, "job_id": jid, "group_id": gid,
                                                "scheduled_at": ahead(1 + i % 5) if st == "INTERVIEWING" else ago(6), "timezone": "America/New_York", "duration_minutes": 60, "mode": "VIDEO",
                                                "round": "Technical", "interviewer": "Hiring Manager", "status": "SCHEDULED" if st == "INTERVIEWING" else "COMPLETED", "version": 1,
                                                "reschedule_history": [{"from": ahead(0), "from_tz": "America/Chicago", "to": ahead(1 + i % 5), "to_tz": "America/New_York", "reason": "Client conflict", "by": "Rita Shah", "at": ago(1)}] if st == "INTERVIEWING" else [],
                                                "created_by": users["recruiter"], "created_at": ago(4)})
            if st in ("OFFERED", "PLACED"):
                ofid = new_id()
                await db.offers.insert_one({"id": ofid, "organization_id": oid, "candidate_id": cid, "submission_id": sid, "job_id": jid, "group_id": gid, "bill_rate": c["bill_rate"], "pay_rate": pay,
                                            "start_date": ahead(14)[:10], "status": "EXTENDED" if st == "OFFERED" else "ACCEPTED", "version": 1, "created_by": users["lead"], "created_at": ago(2)})
                if st == "PLACED":
                    await db.placements.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "offer_id": ofid, "job_id": jid, "group_id": gid, "bill_rate": c["bill_rate"],
                                                    "pay_rate": pay, "start_date": ago(3)[:10], "end_date": ahead(180)[:10], "status": "ACTIVE", "version": 1, "created_by": users["ops"], "created_at": ago(3)})
        if i % 3 == 0:
            await db.notes.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "body": "Strong communication; prefers remote roles.", "visibility": "STANDARD", "author_id": users["recruiter"], "author_name": "Rita Shah", "created_at": ago(3)})
        if i % 4 == 0:
            await db.notes.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "body": "Payroll: confirm W2 vs C2C before offer.", "visibility": "OPERATIONS_ONLY", "author_id": users["ops"], "author_name": "Olivia Park", "created_at": ago(2)})
        if i % 5 == 0:
            await db.tasks.insert_one({"id": new_id(), "organization_id": oid, "candidate_id": cid, "title": f"Follow up with {fn} on availability", "assignee_id": users["recruiter"] if gk == "java" else users["ops"],
                                       "due_date": ahead(i % 6)[:10], "priority": random.choice(["HIGH", "MEDIUM", "LOW"]), "status": "OPEN", "created_by": users["lead"], "created_at": ago(1)})
    await db.notifications.insert_one({"id": new_id(), "organization_id": oid, "user_id": users["admin"], "title": "Welcome to BenchOS", "body": "Demo data has been loaded.", "read": False, "created_at": now()})
    await db.settings.insert_one({"organization_id": oid, "bench_aging_warning_days": 14, "bench_aging_critical_days": 30, "weekly_submission_target": 5, "interview_default_timezone": "America/New_York"})


async def seed():
    await ensure_indexes()
    await db.users.update_one({"email": os.environ["ADMIN_EMAIL"].lower(), "is_platform_admin": {"$exists": False}}, {"$set": {"is_platform_admin": True}})
    if await db.organizations.count_documents({}) > 0:
        return
    logger.info("Seeding demo data")
    await seed_org("Acme Consulting", "acme", os.environ["ADMIN_EMAIL"].lower(), os.environ["ADMIN_PASSWORD"], os.environ["ADMIN_MFA_SECRET"])
    await seed_org("Northwind Talent", "northwind", "admin@northwind.test", DEMO_PASSWORD, os.environ["ADMIN_MFA_SECRET"], full=False)
