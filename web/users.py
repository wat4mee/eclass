"""Creating students on first sign-in and deleting them with all their data."""
from datetime import datetime, timezone

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from web.models import Course, Enrollment, User


def signed_in(db: Session, username: str) -> User:
    """The student's row, created on their first sign-in; records the sign-in time."""
    user = db.scalar(select(User).where(User.eclass_username == username))
    if user is None:
        user = User(eclass_username=username)
        db.add(user)
    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
    return user


def delete_user(db: Session, user_id: int) -> None:
    """Remove the student and everything personal (database cascades), then course content nobody uses anymore."""
    db.execute(delete(User).where(User.id == user_id))
    db.execute(delete(Course).where(~exists().where(Enrollment.course_id == Course.id)))
