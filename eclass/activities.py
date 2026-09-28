"""Parsing of course activities and activity pages (assign, folder, url)."""
import copy
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

SUPPORTED_TYPES = {"ubfile", "folder", "url", "assign"}
SKIPPED_TYPES = {"label"}  # inline text, no page of its own


def _clean(text):
    return " ".join(text.split())


def parse_activity(li, course_id, section):
    """Turn an `li.activity` element into an activities-table row (or None)."""
    m = re.fullmatch(r"module-(\d+)", li.get("id", ""))
    types = [c[len("modtype_"):] for c in li.get("class", []) if c.startswith("modtype_")]
    if not m or not types or types[0] in SKIPPED_TYPES:
        return None
    name = None
    inst = li.select_one(".instancename")
    if inst is not None:
        inst = copy.copy(inst)
        for hidden in inst.select(".accesshide"):
            hidden.decompose()
        name = _clean(inst.get_text(" ", strip=True))
    link = li.select_one("a[href*='/mod/']")
    return {
        "id": int(m.group(1)),
        "course_id": course_id,
        "section": section,
        "type": types[0],
        "name": name,
        "url": link["href"] if link else None,
    }


def pluginfile_links(soup, scope="#region-main"):
    """Unique pluginfile.php links inside `scope` (falls back to the whole page)."""
    root = soup.select_one(scope) or soup
    seen, links = set(), []
    for a in root.select("a[href*='pluginfile.php']"):
        href = a["href"]
        if href not in seen:
            seen.add(href)
            links.append(href)
    return links


# Row labels as shown on the assignment page -> assignments-table columns.
_ASSIGN_FIELDS = {
    "due date": "due_date",
    "submission status": "submission_status",
    "grading status": "grading_status",
    "grade": "grade",
}


def parse_assign(soup):
    """Extract due date, statuses, grade, description and attachment links."""
    info = dict.fromkeys(_ASSIGN_FIELDS.values())
    for tr in soup.select("#region-main table tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        key = _clean(cells[0].get_text(" ", strip=True)).lower()
        col = _ASSIGN_FIELDS.get(key)
        if col and info[col] is None:
            info[col] = _clean(cells[-1].get_text(" ", strip=True)) or None
    intro = soup.select_one("#intro")
    info["intro"] = intro.get_text("\n", strip=True) if intro else None
    attachments = pluginfile_links(soup, "#intro") if intro else []
    return info, attachments


def resolve_url(client, view_url):
    """Return the external target of a `url` activity without fetching it."""
    resp = client.get(view_url, allow_redirects=False)
    if resp.is_redirect:
        return urljoin(resp.url, resp.headers["Location"])
    soup = BeautifulSoup(resp.text, "html.parser")
    own_host = urlparse(client.base_url).netloc
    for sel in (".urlworkaround a[href]", "#region-main a[href]"):
        for a in soup.select(sel):
            if urlparse(a["href"]).netloc not in ("", own_host):
                return a["href"]
    return None
