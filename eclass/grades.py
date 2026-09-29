"""Grades as eClass shows them ('22.00 / 25.00')."""
import re


def grade_points(grade: str | None) -> tuple[float, float] | None:
    """'22.00 / 25.00' -> (22.0, 25.0); None when the grade is not a score."""
    m = re.match(r"\s*([\d.]+)\s*/\s*([\d.]+)", grade or "")
    return (float(m.group(1)), float(m.group(2))) if m and float(m.group(2)) else None


def grade_percent(grade: str | None) -> int | None:
    points = grade_points(grade)
    return round(100 * points[0] / points[1]) if points else None
