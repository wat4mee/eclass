"""Course discovery (dashboard) and course-page parsing."""
import re
from urllib.parse import parse_qs, urlparse


def _query_id(href, key="id"):
    vals = parse_qs(urlparse(href).query).get(key)
    return int(vals[0]) if vals and vals[0].isdigit() else None


def _clean(text):
    return " ".join(text.split())


def list_courses(client):
    """Return [{id, name, code, professor}] for courses linked from the dashboard."""
    soup = client.soup("/")
    courses = {}
    for a in soup.select('a[href*="course/view.php?id="]'):
        cid = _query_id(a["href"])
        if cid is None or cid == 1 or cid in courses:
            continue
        h3 = a.select_one(".course-title h3")
        if h3 is None:
            continue
        for badge in h3.select("span.new"):
            badge.decompose()
        title = _clean(h3.get_text(" ", strip=True))
        m = re.match(r"(.*?)\s*\[([^\]]+)\]\s*$", title)
        name, code = (m.group(1), m.group(2)) if m else (title, None)
        prof = a.select_one(".course-title .prof")
        courses[cid] = {
            "id": cid,
            "name": name,
            "code": code,
            "professor": _clean(prof.get_text()) if prof else None,
        }
    return [courses[cid] for cid in sorted(courses)]


def parse_course_page(soup):
    """Return [{number, name, activities: [li.activity, ...]}] in section order.

    The Coursemos theme repeats the current week at the top of the page, so
    sections are de-duplicated by their `section-N` id.
    """
    sections = {}
    for li in soup.select("li.section"):
        m = re.fullmatch(r"section-(\d+)", li.get("id", ""))
        if not m or int(m.group(1)) in sections:
            continue
        name_el = li.select_one(".sectionname")
        sections[int(m.group(1))] = {
            "number": int(m.group(1)),
            "name": _clean(name_el.get_text(" ", strip=True)) if name_el else None,
            "activities": li.select("li.activity"),
        }
    return [sections[n] for n in sorted(sections)]
