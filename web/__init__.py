"""Hosted multi-user version of the dashboard (Render + Neon Postgres).

    flask --app web run            # local development (Homebrew Postgres, database eclass_web_dev)

The single-user Mac version (app.py, SQLite) is separate and unchanged; both reuse the eclass/ package.
"""
from flask import Flask, jsonify
from sqlalchemy import text

from web import config, db


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(config.from_env())
    app.config.update(overrides or {})
    engine = db.make_engine(app.config["DATABASE_URL"])
    app.extensions["db_engine"] = engine
    app.extensions["db_sessions"] = db.make_session_factory(engine)
    app.teardown_appcontext(db.close_session)

    @app.get("/healthz")
    def healthz():
        """Render's health check: the app is up and the database answers."""
        db.session().execute(text("SELECT 1"))
        return jsonify(status="ok")

    return app
