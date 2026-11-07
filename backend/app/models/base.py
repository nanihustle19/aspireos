import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

def new_uuid():
    return str(uuid.uuid4())

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=True)

class BaseModel(Base, TimestampMixin):
    __abstract__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
