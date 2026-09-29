"""The public privacy page."""
from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.get("/privacy")
def privacy():
    return render_template("privacy.html")
