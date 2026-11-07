# Organization roles
ADMIN = "ADMIN"
OPERATIONS = "OPERATIONS"
EMPLOYEE = "EMPLOYEE"
AUDITOR = "AUDITOR"
ORG_ROLES = [ADMIN, OPERATIONS, EMPLOYEE, AUDITOR]

# Group roles
GROUP_ROLES = ["LEAD", "RECRUITER", "MARKETING", "VIEWER"]

# Candidate statuses
STATUSES = [
    "NEW", "BENCH", "MARKETING", "SUBMITTED", "INTERVIEWING",
    "OFFERED", "PLACED", "ON_HOLD", "ARCHIVED",
]
MARKETING_STATES = ["MARKETING", "SUBMITTED", "INTERVIEWING", "OFFERED"]

# Valid status transitions (state machine)
TRANSITIONS: dict[str, list[str]] = {
    "NEW": ["BENCH", "ON_HOLD"],
    "BENCH": ["MARKETING", "ON_HOLD"],
    "MARKETING": ["SUBMITTED", "BENCH", "ON_HOLD"],
    "SUBMITTED": ["INTERVIEWING", "MARKETING"],
    "INTERVIEWING": ["OFFERED", "MARKETING"],
    "OFFERED": ["PLACED", "MARKETING"],
    "PLACED": ["BENCH"],
    "ON_HOLD": ["BENCH"],
    "ARCHIVED": [],
}

# Rate field visibility
PAY_FIELDS = ["pay_rate"]
BILL_FIELDS = ["bill_rate", "target_rate", "submission_rate", "rate"]

# Candidate fields editable by role
FULL_FIELDS = [
    "first_name", "last_name", "email", "phone", "location", "primary_skill", "skills",
    "experience_years", "visa_status", "work_authorization", "availability_date", "source",
    "linkedin_url", "pay_rate", "bill_rate", "target_rate", "summary", "relocation", "timezone",
]
MARKETING_FIELDS = ["skills", "availability_date", "target_rate", "summary", "relocation", "location"]

# Document handling
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "rtf", "png", "jpg", "jpeg"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

# Pipeline statuses
SUBMISSION_STATUSES = ["SUBMITTED", "CLIENT_REVIEW", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN", "PLACED"]
INTERVIEW_STATUSES = ["SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW"]
OFFER_STATUSES = ["EXTENDED", "ACCEPTED", "DECLINED", "WITHDRAWN"]

# Default org settings
DEFAULT_SETTINGS = {
    "bench_aging_warning_days": 14,
    "bench_aging_critical_days": 30,
    "weekly_submission_target": 5,
    "interview_default_timezone": "America/New_York",
    "mfa_required_for_admin": True,
}
