"""The account page and "Disconnect & delete my data"."""
import logging

from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms import BooleanField
from wtforms.validators import DataRequired

from web import db as database
from web import users
from web.views import T

bp = Blueprint("account", __name__)
log = logging.getLogger("web.account")


class DeleteForm(FlaskForm):
    confirm = BooleanField(validators=[DataRequired()])


@bp.get("/account")
@login_required
def account():
    return render_template("account.html", form=DeleteForm(), error=None)


@bp.post("/account/delete")
@login_required
def delete():
    form = DeleteForm()
    if not form.validate():
        return render_template("account.html", form=form, error=T("web.delete.need_confirm")), 400
    user_id = current_user.id
    db = database.session()
    users.delete_user(db, user_id)
    db.commit()
    session.clear()
    logout_user()  # after clear(): it marks the "remember me" cookie for deletion in the session
    flash(T("web.delete.done"), "ok")
    log.info("user %s deleted their account and data", user_id)
    return redirect(url_for("auth.login"))
