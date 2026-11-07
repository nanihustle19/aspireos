from sqlalchemy import String, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class Group(BaseModel):
    __tablename__ = "groups"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Membership(BaseModel):
    __tablename__ = "memberships"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # LEAD, RECRUITER, MARKETING, VIEWER
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    ended_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
