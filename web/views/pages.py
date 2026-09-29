"""Home (signed-in students) and the public privacy page."""
from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint("pages", __name__)


@bp.get("/")
@login_required
def home():
    return render_template("home.html")


@bp.get("/privacy")
def privacy():
    return render_template("privacy.html")
