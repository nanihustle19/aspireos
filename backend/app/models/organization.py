from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class Organization(BaseModel):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(50), default="Professional")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    logo_data: Mapped[str | None] = mapped_column(Text, nullable=True)
