import uuid
from datetime import datetime, timezone
from sqlalchemy import Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    search_queries_used: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sources_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_facts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    raw_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    topic: Mapped["Topic"] = relationship("Topic", back_populates="check_results")
