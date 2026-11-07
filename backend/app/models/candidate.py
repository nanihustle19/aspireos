from sqlalchemy import String, Boolean, Integer, Float, Text, ForeignKey, Index, ARRAY, text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class Candidate(BaseModel):
    __tablename__ = "candidates"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_norm: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_norm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_skill: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    visa_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_authorization: Mapped[str | None] = mapped_column(String(50), nullable=True)
    availability_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pay_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    bill_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    relocation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="NEW")
    prior_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("groups.id"), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    bench_since: Mapped[str | None] = mapped_column(String(50), nullable=True)
    archived_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    __table_args__ = (
        Index("idx_candidate_org_status", "organization_id", "status"),
        Index("idx_candidate_org_group", "organization_id", "current_group_id"),
        Index("idx_candidate_org_email", "organization_id", "email_norm"),
        Index("idx_candidate_org_phone", "organization_id", "phone_norm"),
        Index("idx_candidate_org_updated", "organization_id", "updated_at"),
    )

class CandidateGroupAssignment(BaseModel):
    __tablename__ = "candidate_group_assignments"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    started_at: Mapped[str] = mapped_column(String(50))
    started_by: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        # CRITICAL: Partial unique index for one-active-group constraint
        Index("idx_one_active_group", "candidate_id", unique=True, postgresql_where=text("active = true")),
    )
