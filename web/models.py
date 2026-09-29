"""Database tables of the hosted app.

Course content (courses, activities, materials, their text and study packs) is stored once per eClass course and
shared by the students enrolled in it. Everything personal (login, eClass session, enrollments, deadlines, grades,
progress, sync history, AI usage) belongs to one user and is removed with that user (ON DELETE CASCADE).
A student reaches course content only through their own row in `enrollments`.
"""
from datetime import date, datetime

from flask_login import UserMixin
from sqlalchemy import (BigInteger, CheckConstraint, Computed, Date, DateTime, ForeignKey, Identity, Index, Integer,
                        MetaData, String, Text, UniqueConstraint, false, func, text)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {  # stable constraint names, so Alembic migrations can refer to them
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _created():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _user_fk(primary_key=False):
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=primary_key, index=not primary_key)


# ---------------------------------------------------------------- people

class User(UserMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    eclass_username: Mapped[str] = mapped_column(String(100), unique=True)  # Moodle usernames are lowercase
    display_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("eclass_username = lower(btrim(eclass_username)) AND eclass_username <> ''",
                        name="username_normalized"),
    )


class EClassCredential(Base):
    """The student's eClass password, Fernet-encrypted, only when they opted into background sync."""
    __tablename__ = "eclass_credentials"
    user_id: Mapped[int] = _user_fk(primary_key=True)
    encrypted_password: Mapped[str | None] = mapped_column(Text)
    key_version: Mapped[int | None] = mapped_column(Integer)  # which CREDENTIAL_KEY encrypted it (rotation)
    autosync_enabled: Mapped[bool] = mapped_column(default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    __table_args__ = (
        CheckConstraint("status IN ('active', 'invalid')", name="status"),
        CheckConstraint("(encrypted_password IS NULL) = (key_version IS NULL)", name="key_version_with_password"),
        CheckConstraint("NOT autosync_enabled OR encrypted_password IS NOT NULL", name="autosync_needs_password"),
    )


class EClassSession(Base):
    """A short-lived eClass session cookie (encrypted) while the student uses the site; never kept long-term."""
    __tablename__ = "eclass_sessions"
    user_id: Mapped[int] = _user_fk(primary_key=True)
    encrypted_cookie: Mapped[str] = mapped_column(Text)
    key_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


# ---------------------------------------------------------------- shared course content

class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # eClass course id
    name: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(String(60))
    professor: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime] = _created()


class Enrollment(Base):
    """Proof, from the student's own eClass login, that they may see a course."""
    __tablename__ = "enrollments"
    user_id: Mapped[int] = _user_fk(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True, index=True)
    last_seen_at: Mapped[datetime] = _created()


class Section(Base):
    __tablename__ = "sections"
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # Moodle course-module id
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section: Mapped[int | None] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(30))  # ubfile, folder, url, assign, ubboard...
    name: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    intro: Mapped[str | None] = mapped_column(Text)  # assignment description
    first_seen_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime] = _created()


class Material(Base):
    """A file on eClass: metadata and link only. The file itself is never stored (streamed on demand)."""
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(Text)
    eclass_url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))  # of the version the text was extracted from
    size: Mapped[int | None] = mapped_column(BigInteger)
    mimetype: Mapped[str | None] = mapped_column(String(120))
    n_pages: Mapped[int | None] = mapped_column(Integer)
    n_chars: Mapped[int | None] = mapped_column(Integer)
    extract_error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = _created()
    __table_args__ = (UniqueConstraint("activity_id", "filename", name="uq_materials_activity_filename"),)


class MaterialPage(Base):
    """Extracted text of one page or slide, with a full-text index for the chat and search."""
    __tablename__ = "material_pages"
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    __table_args__ = (Index("ix_material_pages_tsv", "tsv", postgresql_using="gin"),)


class StudyPack(Base):
    """AI summary, key concepts, flashcards and quiz of one material version, shared by its students."""
    __tablename__ = "study_packs"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"))
    sha256: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(5))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    concepts: Mapped[list] = mapped_column(JSONB)
    flashcards: Mapped[list] = mapped_column(JSONB)
    quiz: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (UniqueConstraint("material_id", "language", name="uq_study_packs_material_language"),)


class PackNote(Base):
    """Notes per chunk of a long material, so a pack interrupted by the AI quota resumes where it stopped."""
    __tablename__ = "pack_notes"
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    chunk: Mapped[int] = mapped_column(Integer, primary_key=True)
    notes: Mapped[str] = mapped_column(Text)


# ---------------------------------------------------------------- personal data

class UserAssignment(Base):
    """A student's own deadline, submission status and grade for one assignment."""
    __tablename__ = "user_assignments"
    user_id: Mapped[int] = _user_fk(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_text: Mapped[str | None] = mapped_column(String(40))  # as eClass shows it, e.g. '2026-09-25 15:00'
    submission_status: Mapped[str | None] = mapped_column(Text)
    grading_status: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str | None] = mapped_column(Text)  # e.g. '22.00 / 25.00'
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class Progress(Base):
    """Materials the student marked as studied."""
    __tablename__ = "progress"
    user_id: Mapped[int] = _user_fk(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True)
    studied_at: Mapped[datetime] = _created()


class SyncRun(Base):
    """One sync attempt of one student; error_summary is redacted and never holds credentials."""
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int] = _user_fk()
    trigger: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="running", server_default="running")
    error_code: Mapped[str | None] = mapped_column(String(20))  # eclass.auth.EClassError.code
    error_summary: Mapped[str | None] = mapped_column(Text)
    new_items: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    __table_args__ = (
        CheckConstraint("trigger IN ('login', 'button', 'schedule')", name="trigger"),
        CheckConstraint("status IN ('running', 'done', 'error')", name="status"),
    )


class AIUsage(Base):
    """AI requests per student per day, for the daily limit that protects the shared Gemini quota."""
    __tablename__ = "ai_usage"
    user_id: Mapped[int] = _user_fk(primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    __table_args__ = (CheckConstraint("count >= 0", name="count_not_negative"),)
