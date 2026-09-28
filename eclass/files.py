"""Downloading ubfile / folder / assignment attachments with sha256 de-duplication."""
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from . import db
from .activities import pluginfile_links

CHUNK = 64 * 1024


def safe_name(text, max_len=120):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text or "").strip(" .")
    return (text or "untitled")[:max_len]


def section_dir(root, course_name, section_number, section_name):
    return Path(root) / safe_name(course_name) / safe_name(f"{section_number:02d} {section_name or ''}")


def _fix_header(value):
    # requests decodes headers as latin-1; eClass may send raw UTF-8 bytes.
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _name_from_url(url):
    return unquote(Path(urlparse(url).path).name)


def filename_from_response(resp):
    cd = _fix_header(resp.headers.get("Content-Disposition", ""))
    m = re.search(r"filename\*\s*=\s*[\w-]+'[^']*'([^;]+)", cd, re.I)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I) or re.search(
        r"filename\s*=\s*([^;]+)", cd, re.I
    )
    if m:
        return unquote(m.group(1).strip())
    return _name_from_url(resp.url)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_intact(row):
    """True if a recorded file is still on disk with the recorded hash."""
    return os.path.isfile(row["path"]) and sha256_of(row["path"]) == row["sha256"]


def _target_path(conn, activity_id, dest_dir, filename):
    """Pick a path in dest_dir; avoid clobbering another activity's file."""
    path = Path(dest_dir) / safe_name(filename, 200)
    owner = db.path_owner(conn, str(path))
    if owner is not None and owner != activity_id:
        path = path.with_name(f"{path.stem} [{activity_id}]{path.suffix}")
    return path


def save_response(conn, activity_id, resp, dest_dir, filename=None):
    """Stream a file response to disk. Returns 'new', 'updated' or 'unchanged'."""
    filename = filename or filename_from_response(resp)
    path = _target_path(conn, activity_id, dest_dir, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    h, size = hashlib.sha256(), 0
    try:
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(CHUNK):
                f.write(chunk)
                h.update(chunk)
                size += len(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        resp.close()
    digest = h.hexdigest()
    if path.exists() and sha256_of(path) == digest:
        tmp.unlink()
        status = "unchanged"
    else:
        status = "updated" if path.exists() else "new"
        os.replace(tmp, path)
    known = {r["filename"]: r for r in db.get_files(conn, activity_id)}
    if status != "unchanged" or filename not in known or known[filename]["sha256"] != digest:
        db.upsert_file(conn, activity_id, filename, str(path), digest, size, resp.url)
    return status


def download_links(client, conn, activity_id, urls, dest_dir, refresh=False):
    """Download pluginfile URLs; files already on disk with a matching hash are skipped."""
    known = {r["filename"]: r for r in db.get_files(conn, activity_id)}
    results = []
    for url in urls:
        name = _name_from_url(url)
        row = known.get(name)
        if row is not None and not refresh and _is_intact(row):
            results.append("skipped")
            continue
        resp = client.get(url, stream=True)
        results.append(save_response(conn, activity_id, resp, dest_dir, name))
    return results


def download_ubfile(client, conn, activity, dest_dir, refresh=False):
    """ubfile view.php redirects straight to the file (or, rarely, to a page of links)."""
    rows = db.get_files(conn, activity["id"])
    if rows and not refresh and all(_is_intact(r) for r in rows):
        return ["skipped"] * len(rows)
    resp = client.get(activity["url"], stream=True)
    is_page = "pluginfile.php" not in resp.url and resp.headers.get(
        "Content-Type", ""
    ).startswith("text/html")
    if not is_page:
        return [save_response(conn, activity["id"], resp, dest_dir)]
    soup = BeautifulSoup(resp.text, "html.parser")
    resp.close()
    return download_links(client, conn, activity["id"], pluginfile_links(soup), dest_dir, refresh)
