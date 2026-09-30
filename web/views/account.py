"""The account page: background sync on/off and "Disconnect & delete my data"."""
import logging

from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, logout_user
from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import BooleanField, PasswordField
from wtforms.validators import DataRequired, InputRequired, Length

from web import autosync, eclass_login, users
from web import db as database
from web.extensions import limiter
from web.models import SyncRun
from web.views import T

bp = Blueprint("account", __name__)
log = logging.getLogger("web.account")


class DeleteForm(FlaskForm):
    confirm = BooleanField(validators=[DataRequired()])


class AutosyncForm(FlaskForm):
    password = PasswordField(validators=[InputRequired(), Length(max=256)])


def _page(status: int = 200, form=None, error=None, sync_error=None):
    db = database.session()
    last = db.scalar(select(SyncRun.finished_at).where(SyncRun.user_id == current_user.id,
                                                       SyncRun.trigger == "schedule", SyncRun.status == "done")
                     .order_by(SyncRun.id.desc()).limit(1))
    return render_template("account.html", form=form or DeleteForm(), error=error, sync_form=AutosyncForm(),
                           sync_error=sync_error, autosync=autosync.state(db, current_user.id),
                           last_background=last), status


@bp.get("/account")
@login_required
def account():
    return _page()


def _account_key() -> str:
    return f"user:{current_user.eclass_username}"


@bp.post("/account/autosync")
@login_required
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_IP"])
@limiter.limit(lambda: current_app.config["LOGIN_LIMIT_USER"], key_func=_account_key)
def autosync_on():
    """Turn background sync on: the password is checked with eClass first, then stored encrypted."""
    form = AutosyncForm()
    if not form.validate():
        return _page(400, sync_error=T("web.login.missing"))
    try:
        cookies = eclass_login.check_login(current_user.eclass_username, form.password.data)
    except eclass_login.LoginFailed as exc:
        key, status = ("web.login.failed", 401) if exc.reason == "credentials" else ("web.login.unreachable", 503)
        return _page(status, sync_error=T(key))
    db = database.session()
    autosync.enable(db, current_user.id, form.password.data)
    eclass_login.save_session(db, current_user.id, cookies, current_app.config["ECLASS_SESSION_MINUTES"])
    db.commit()
    log.info("user %s turned background sync on", current_user.id)
    flash(T("web.autosync.turned_on"), "ok")
    return redirect(url_for("account.account") + "#autosync")


@bp.post("/account/autosync/off")
@login_required
def autosync_off():
    db = database.session()
    autosync.disable(db, current_user.id)
    db.commit()
    log.info("user %s turned background sync off", current_user.id)
    flash(T("web.autosync.turned_off"), "ok")
    return redirect(url_for("account.account") + "#autosync")


@bp.post("/account/delete")
@login_required
def delete():
    form = DeleteForm()
    if not form.validate():
        return _page(400, form=form, error=T("web.delete.need_confirm"))
    user_id = current_user.id
    db = database.session()
    users.delete_user(db, user_id)
    db.commit()
    session.clear()
    logout_user()  # after clear(): it marks the "remember me" cookie for deletion in the session
    flash(T("web.delete.done"), "ok")
    log.info("user %s deleted their account and data", user_id)
    return redirect(url_for("auth.login"))
