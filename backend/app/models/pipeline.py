from sqlalchemy import String, Integer, Float, Text, ForeignKey, ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class Vendor(BaseModel):
    __tablename__ = "vendors"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

class Client(BaseModel):
    __tablename__ = "clients"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

class Job(BaseModel):
    __tablename__ = "jobs"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    client_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("clients.id"), nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vendors.id"), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    openings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

class Submission(BaseModel):
    __tablename__ = "submissions"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    client_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("clients.id"), nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vendors.id"), nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("groups.id"), nullable=True)
    submission_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SUBMITTED")
    status_history: Mapped[list | None] = mapped_column(JSON, default=list)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    
    __table_args__ = ({"schema": None},)

class Interview(BaseModel):
    __tablename__ = "interviews"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id"))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("groups.id"), nullable=True)
    scheduled_at: Mapped[str] = mapped_column(String(50))
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    mode: Mapped[str] = mapped_column(String(20), default="VIDEO")
    round: Mapped[str] = mapped_column(String(50), default="Round 1")
    interviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED")
    reschedule_history: Mapped[list | None] = mapped_column(JSON, default=list)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

class Offer(BaseModel):
    __tablename__ = "offers"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("submissions.id"))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("groups.id"), nullable=True)
    bill_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    pay_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="EXTENDED")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

class Placement(BaseModel):
    __tablename__ = "placements"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id"), index=True)
    offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("offers.id"), unique=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("groups.id"), nullable=True)
    bill_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    pay_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[str] = mapped_column(String(20))
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    ended_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
