import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class TopicStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    search_keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    check_interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    has_update: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[TopicStatus] = mapped_column(
        SAEnum(TopicStatus, name="topicstatus"), default=TopicStatus.active, nullable=False
    )
    source_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="topics")
    facts: Mapped[list["Fact"]] = relationship("Fact", back_populates="topic", cascade="all, delete-orphan")
    check_results: Mapped[list["CheckResult"]] = relationship(
        "CheckResult", back_populates="topic", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="topic", cascade="all, delete-orphan"
    )
