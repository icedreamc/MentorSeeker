from datetime import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class SearchJob(Base):
    __tablename__ = "search_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    school: Mapped[str] = mapped_column(String(255), nullable=False)
    interested_field: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    max_steps: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    target_mentor_count: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    enrich_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    progress_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_output_file: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    enriched_output_file: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mentor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
