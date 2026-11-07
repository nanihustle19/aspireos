from sqlalchemy import String, Boolean, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class AuditLog(BaseModel):
    __tablename__ = "audit_logs"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    actor_id: Mapped[str] = mapped_column(String(36))
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index("idx_audit_org_created", "organization_id", "created_at"),
    )

class TimelineEvent(BaseModel):
    __tablename__ = "timeline_events"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    event: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Notification(BaseModel):
    __tablename__ = "notifications"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)

class EmailOutbox(BaseModel):
    __tablename__ = "email_outbox"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    to: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    sent_at: Mapped[str | None] = mapped_column(String(50), nullable=True)

class Note(BaseModel):
    __tablename__ = "notes"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(20), default="STANDARD")  # STANDARD, OPERATIONS_ONLY
    author_id: Mapped[str] = mapped_column(String(36))
    author_name: Mapped[str] = mapped_column(String(255))

class Task(BaseModel):
    __tablename__ = "tasks"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("candidates.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    assignee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    created_by: Mapped[str] = mapped_column(String(36))

class Document(BaseModel):
    __tablename__ = "documents"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(50), default="RESUME")
    version: Mapped[int] = mapped_column(default=1)
    original_filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[int] = mapped_column(default=0)
    storage_path: Mapped[str] = mapped_column(Text)
    scan_status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, PASSED, FAILED
    scan_engine: Mapped[str] = mapped_column(String(20), default="SIMULATED")
    scan_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scanned_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[str] = mapped_column(String(36))
    uploaded_by_name: Mapped[str] = mapped_column(String(255))

class BackgroundJob(BaseModel):
    __tablename__ = "background_jobs"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_csv: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36))
    created_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

class SavedView(BaseModel):
    __tablename__ = "saved_views"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    page: Mapped[str] = mapped_column(String(50), default="candidates")
    filters: Mapped[dict | None] = mapped_column(JSON, default=dict)

class Settings(BaseModel):
    __tablename__ = "settings"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), unique=True)
    bench_aging_warning_days: Mapped[int] = mapped_column(default=14)
    bench_aging_critical_days: Mapped[int] = mapped_column(default=30)
    weekly_submission_target: Mapped[int] = mapped_column(default=5)
    interview_default_timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")
