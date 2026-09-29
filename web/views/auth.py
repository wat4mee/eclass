"""Sign-in with the student's eClass login (proxy login) and sign-out."""
import logging

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import InputRequired, Length

from web import db as database
from web import eclass_login, users
from web.extensions import limiter
from web.views import T

bp = Blueprint("auth", __name__)
log = logging.getLogger("web.auth")

MESSAGES = {"credentials": ("web.login.failed", 401), "unreachable": ("web.login.unreachable", 503),
            "missing": ("web.login.missing", 400)}


class LoginForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(max=100)])
    password = PasswordField(validators=[InputRequired(), Length(max=256)])


def _username_key() -> str:
    """Rate-limit key per eClass username, so one account cannot be guessed at from many IPs."""
    name = eclass_login.normalize_username(request.form.get("username", ""))
    return f"user:{name}" if name else get_remote_address()


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_IP"], methods=["POST"])
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_USER"], key_func=_username_key, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("pages.home"))
    form, error = LoginForm(), None
    if request.method == "POST":
        if not form.validate():  # the CSRF token was already checked by CSRFProtect
            error = "missing"
        else:
            username = eclass_login.normalize_username(form.username.data)
            try:
                cookies = eclass_login.check_login(username, form.password.data)
            except eclass_login.LoginFailed as exc:
                error = exc.reason
            else:
                db = database.session()
                user = users.signed_in(db, username)
                eclass_login.save_session(db, user.id, cookies, current_app.config["ECLASS_SESSION_MINUTES"])
                db.commit()
                session.clear()  # a fresh session at sign-in (no session fixation)
                login_user(user, remember=True)
                log.info("user %s signed in", user.id)
                return redirect(url_for("pages.home"))
        form.password.data = ""  # never send the password back to the page
    message, status = MESSAGES.get(error, (None, 200))
    return render_template("login.html", form=form, error=T(message) if message else None), status


@bp.post("/logout")
@login_required
def logout():
    db = database.session()
    eclass_login.drop_session(db, current_user.id)
    db.commit()
    session.clear()
    logout_user()  # after clear(): it marks the "remember me" cookie for deletion in the session
    flash(T("web.logged_out"), "ok")
    return redirect(url_for("auth.login"))
