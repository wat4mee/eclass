"""What the pages show: a student's courses, deadlines, grades and materials, always through their enrollments."""
import calendar
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eclass import i18n as base_i18n
from eclass.grades import grade_percent, grade_points
from eclass.notify import is_submitted
from web.models import Activity, Course, Enrollment, Material, Section, StudyPack, UserAssignment

TZ = ZoneInfo("Asia/Tashkent")  # the students' time zone: shown dates, the greeting, "this week"
SOON = timedelta(hours=48)  # an unsubmitted assignment due within this is "soon"
RING = timedelta(days=7)  # the countdown ring on the home page is full a week before a deadline
STATE_ORDER = {"overdue": 0, "soon": 1, "upcoming": 2, "nodate": 3, "done": 4}
COURSE_COLORS = ["#f59e0b", "#14b8a6", "#f97360", "#3b82f6", "#84cc16", "#ec4899", "#8b5cf6", "#06b6d4"]
WEEK = re.compile(r"^(\d+)\s*Week\s*\[(\d{1,2})\s+([A-Za-z]+)\s*-\s*(\d{1,2})\s+([A-Za-z]+)\]", re.I)
MONTHS = {name.lower(): n for n, name in enumerate(calendar.month_name) if name}


def _mine(user_id: int):
    """Join condition: only courses this student is enrolled in."""
    return (Enrollment.course_id == Course.id) & (Enrollment.user_id == user_id)


def courses(db: Session, user_id: int) -> list[dict]:
    n_materials = (select(func.count(Material.id)).join(Activity, Activity.id == Material.activity_id)
                   .where(Activity.course_id == Course.id).scalar_subquery())
    n_assign = (select(func.count(Activity.id)).where(Activity.course_id == Course.id, Activity.type == "assign")
                .scalar_subquery())
    n_packs = (select(func.count(func.distinct(StudyPack.material_id)))
               .join(Material, (Material.id == StudyPack.material_id) & (Material.sha256 == StudyPack.sha256))
               .join(Activity, Activity.id == Material.activity_id).where(Activity.course_id == Course.id)
               .scalar_subquery())
    rows = db.execute(select(Course, n_materials, n_assign, n_packs).join(Enrollment, _mine(user_id))
                      .order_by(Course.name))
    return [{"id": c.id, "name": c.name, "professor": c.professor, "n_materials": m, "n_assign": a, "n_packs": p}
            for c, m, a, p in rows]


def colors(db: Session, user_id: int) -> dict[int, str]:
    """One accent color per course of this student, stable while their course list stays the same."""
    ids = sorted(db.scalars(select(Enrollment.course_id).where(Enrollment.user_id == user_id)))
    return {cid: COURSE_COLORS[i % len(COURSE_COLORS)] for i, cid in enumerate(ids)}


def course(db: Session, user_id: int, course_id: int) -> Course | None:
    return db.scalar(select(Course).join(Enrollment, _mine(user_id)).where(Course.id == course_id))


def assignments(db: Session, user_id: int, lang: str, course_id: int | None = None) -> list[dict]:
    query = (select(UserAssignment, Activity, Course).join(Activity, Activity.id == UserAssignment.activity_id)
             .join(Course, Course.id == Activity.course_id).join(Enrollment, _mine(user_id))
             .where(UserAssignment.user_id == user_id))
    if course_id is not None:
        query = query.where(Course.id == course_id)
    now, items = datetime.now(timezone.utc), []
    for mine, activity, crs in db.execute(query):
        due = mine.due_at
        if is_submitted(mine.submission_status):
            state = "done"
        elif due is None:
            state = "nodate"
        else:
            state = "overdue" if due < now else "soon" if due - now <= SOON else "upcoming"
        left = due - now if due and due > now else None
        items.append({"activity_id": activity.id, "name": activity.name, "url": activity.url, "course_id": crs.id,
                      "course": crs.name, "state": state, "due": due, "due_text": mine.due_text,
                      "due_iso": due.isoformat() if due else None,
                      "left": base_i18n.duration(lang, left) if left else None,
                      "ring": min(1.0, left / RING) if left else 0.0,
                      "days_left": left.days if left else 0,
                      "hours_left": int(left.total_seconds() // 3600) if left else 0,
                      "grade": mine.grade, "pct": grade_percent(mine.grade), "status": mine.submission_status,
                      "grading": mine.grading_status})
    far = datetime.max.replace(tzinfo=timezone.utc)
    items.sort(key=lambda d: (STATE_ORDER[d["state"]], d["due"] or far))
    return items


def recent_materials(db: Session, user_id: int, limit: int = 8) -> list[dict]:
    rows = db.execute(select(Material, Activity, Course).join(Activity, Activity.id == Material.activity_id)
                      .join(Course, Course.id == Activity.course_id).join(Enrollment, _mine(user_id))
                      .order_by(Material.first_seen_at.desc(), Material.id.desc()).limit(limit))
    return [{"id": m.id, "filename": m.filename, "activity": a.name, "course_id": c.id, "course": c.name}
            for m, a, c in rows]


def week_info(name: str | None, lang: str, today: date) -> dict:
    """'3Week [19 September - 25 September]' -> localized title, date range and whether it is this week."""
    m = WEEK.match(name or "")
    if not m:
        general = not name or name.lower().startswith("course")
        return {"title": base_i18n.t(lang, "week.general") if general else name, "range": None, "current": False}
    number, d1, m1, d2, m2 = m.groups()
    title = base_i18n.t(lang, "week.n", n=number)
    try:
        start = date(today.year, MONTHS[m1.lower()], int(d1))
        end = date(today.year, MONTHS[m2.lower()], int(d2))
    except (KeyError, ValueError):
        return {"title": title, "range": None, "current": False}
    if end < start:  # a week crossing New Year
        end = end.replace(year=end.year + 1)
    return {"title": title, "range": base_i18n.day_range(lang, start, end), "current": start <= today <= end}


def course_page(db: Session, user_id: int, course_id: int, lang: str) -> dict | None:
    crs = course(db, user_id, course_id)
    if crs is None:
        return None
    activities = db.scalars(select(Activity).where(Activity.course_id == course_id)
                            .order_by(Activity.section, Activity.id)).all()
    files: dict[int, list] = {}
    for m in db.scalars(select(Material).join(Activity, Activity.id == Material.activity_id)
                        .where(Activity.course_id == course_id).order_by(Material.filename)):
        files.setdefault(m.activity_id, []).append(m)
    mine = {a["activity_id"]: a for a in assignments(db, user_id, lang, course_id)}
    by_section: dict[int, list] = {}
    for a in activities:
        by_section.setdefault(a.section, []).append(a)
    weeks, today = [], datetime.now(TZ).date()
    for section in db.scalars(select(Section).where(Section.course_id == course_id).order_by(Section.number)):
        if by_section.get(section.number):
            weeks.append(week_info(section.name, lang, today) | {"number": section.number,
                                                                  "activities": by_section[section.number]})
    counts = {"files": sum(len(f) for f in files.values()),
              "assign": sum(a.type == "assign" for a in activities)}
    return {"course": crs, "weeks": weeks, "files": files, "assignments": mine, "counts": counts}


def average(items: list[dict]) -> int | None:
    pcts = [d["pct"] for d in items if d["pct"] is not None]
    return round(sum(pcts) / len(pcts)) if pcts else None


def home_stats(items: list[dict], course_list: list[dict]) -> dict:
    return {"pending": sum(d["state"] != "done" for d in items), "avg": average(items),
            "materials": sum(c["n_materials"] for c in course_list), "courses": len(course_list),
            "packs": sum(c["n_packs"] for c in course_list)}


def grade_summary(items: list[dict]) -> dict:
    return {"avg": average(items), "graded": sum(d["pct"] is not None for d in items),
            "done": sum(d["state"] == "done" for d in items), "total": len(items)}


def grades(db: Session, user_id: int, lang: str, items: list[dict] | None = None) -> list[dict]:
    groups: dict[int, dict] = {}
    for item in assignments(db, user_id, lang) if items is None else items:
        group = groups.setdefault(item["course_id"], {"course_id": item["course_id"], "course": item["course"],
                                                      "graded": [], "ungraded": [], "earned": 0.0, "possible": 0.0})
        (group["graded"] if item["grade"] else group["ungraded"]).append(item)
        points = grade_points(item["grade"])
        if points:
            group["earned"] += points[0]
            group["possible"] += points[1]
    for group in groups.values():
        group["pct"] = round(100 * group["earned"] / group["possible"]) if group["possible"] else None
        group["avg"] = average(group["graded"])
    return sorted(groups.values(), key=lambda g: (g["pct"] is None, g["course"]))


def material_for(db: Session, user_id: int, material_id: int) -> Material | None:
    """The material, only if it belongs to a course the student is enrolled in."""
    return db.scalar(select(Material).join(Activity, Activity.id == Material.activity_id)
                     .join(Course, Course.id == Activity.course_id).join(Enrollment, _mine(user_id))
                     .where(Material.id == material_id))
