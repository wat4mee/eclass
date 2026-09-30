"""Sign-in with the student's eClass login (proxy login) and sign-out."""
import logging

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import InputRequired, Length

from web import autosync, eclass_login, tasks, users
from web import db as database
from web.extensions import limiter
from web.views import T

bp = Blueprint("auth", __name__)
log = logging.getLogger("web.auth")

MESSAGES = {"credentials": ("web.login.failed", 401), "unreachable": ("web.login.unreachable", 503),
            "missing": ("web.login.missing", 400)}


class LoginForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(max=100)])
    password = PasswordField(validators=[InputRequired(), Length(max=256)])
    keep = BooleanField()  # "keep me synced in the background": off unless the student ticks it


def _remember_password(db, user_id: int, password: str, ticked: bool) -> None:
    """Store the (just verified) password when the student ticked the box. If background sync is already on,
    the stored copy is replaced by this current password, so a password changed on eClass keeps working."""
    if ticked or autosync.state(db, user_id) == "on":
        autosync.enable(db, user_id, password)


def _username_key() -> str:
    """Rate-limit key per eClass username, so one account cannot be guessed at from many IPs."""
    name = eclass_login.normalize_username(request.form.get("username", ""))
    return f"user:{name}" if name else get_remote_address()


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_IP"], methods=["POST"])
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_USER"], key_func=_username_key, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))
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
                _remember_password(db, user.id, form.password.data, form.keep.data)
                db.commit()
                session.clear()  # a fresh session at sign-in (no session fixation)
                login_user(user, remember=True)
                log.info("user %s signed in", user.id)
                tasks.start_sync(current_app._get_current_object(), user.id, "login")
                return redirect(url_for("dashboard.home"))
        form.password.data = ""  # never send the password back to the page
    message, status = MESSAGES.get(error, (None, 200))
    return render_template("login.html", form=form, error=T(message) if message else None), status


class ReconnectForm(FlaskForm):
    password = PasswordField(validators=[InputRequired(), Length(max=256)])
    keep = BooleanField()


def _account_key() -> str:
    return f"user:{current_user.eclass_username}" if current_user.is_authenticated else get_remote_address()


@bp.route("/reconnect", methods=["GET", "POST"])
@login_required
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_IP"], methods=["POST"])
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_USER"], key_func=_account_key, methods=["POST"])
def reconnect():
    """The saved eClass session ended (2 hours): the password once more, then refresh."""
    form, error = ReconnectForm(), None
    if request.method == "POST":
        if not form.validate():
            error = "missing"
        else:
            try:
                cookies = eclass_login.check_login(current_user.eclass_username, form.password.data)
            except eclass_login.LoginFailed as exc:
                error = exc.reason
            else:
                db = database.session()
                eclass_login.save_session(db, current_user.id, cookies, current_app.config["ECLASS_SESSION_MINUTES"])
                _remember_password(db, current_user.id, form.password.data, form.keep.data)
                db.commit()
                tasks.start_sync(current_app._get_current_object(), current_user.id, "login")
                return redirect(url_for("dashboard.home"))
        form.password.data = ""
    message, status = MESSAGES.get(error, (None, 200))
    keep = autosync.state(database.session(), current_user.id) != "off"  # re-entering a stopped password: ticked
    return render_template("reconnect.html", form=form, keep=keep, error=T(message) if message else None), status


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
