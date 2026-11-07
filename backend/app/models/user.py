from sqlalchemy import DateTime, String, Boolean, Integer, ForeignKey, Text, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel
from datetime import datetime

class User(BaseModel):
    __tablename__ = "users"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # ADMIN, OPERATIONS, EMPLOYEE, AUDITOR
    status: Mapped[str] = mapped_column(String(20), default="INVITED")  # INVITED, ACTIVE, DEACTIVATED
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_methods: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, default=0)
    picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_ops_only: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    

class Invitation(BaseModel):
    __tablename__ = "invitations"
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, ACCEPTED, REVOKED
    invited_by: Mapped[str] = mapped_column(String(36))
    invited_by_name: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[str] = mapped_column(String(50))
    accepted_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    temporary_password_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_id: Mapped[str | None] = mapped_column(ForeignKey("email_outbox.id"), nullable=True)

class LoginAttempt(BaseModel):
    __tablename__ = "login_attempts"
    identifier: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    last: Mapped[str | None] = mapped_column(String(50), nullable=True)

class PasswordResetToken(BaseModel):
    __tablename__ = "password_reset_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
