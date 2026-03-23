from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Mentor(Base):
    __tablename__ = "mentors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("search_jobs.id", ondelete="SET NULL"), nullable=True)

    school: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    interested_field: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    research_direction: Mapped[str] = mapped_column(Text, default="", nullable=False)

    profile_urls_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    structured_profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    publications_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    papers_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    high_level_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "mentor_id", name="uq_favorites_user_mentor"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mentor_id: Mapped[int] = mapped_column(Integer, ForeignKey("mentors.id", ondelete="CASCADE"), nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MentorNote(Base):
    __tablename__ = "mentor_notes"
    __table_args__ = (UniqueConstraint("user_id", "mentor_id", name="uq_notes_user_mentor"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mentor_id: Mapped[int] = mapped_column(Integer, ForeignKey("mentors.id", ondelete="CASCADE"), nullable=False)

    note_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
