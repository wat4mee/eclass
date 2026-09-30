"""Hosted multi-user version of the dashboard (Render + Neon Postgres).

    flask --app web run            # local development (Homebrew Postgres, database eclass_web_dev)

The single-user Mac version (app.py, SQLite) is separate and unchanged; both reuse the eclass/ package.
"""
import logging
from pathlib import PurePosixPath
from urllib.parse import urlparse

from flask import Flask, abort, g, jsonify, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from eclass import i18n as base_i18n
from eclass.config import ECLASS_URL

from web import config, crypto, db, i18n, redact
from web import dashboard as data
from web.extensions import csrf, limiter, login_manager
from web.models import User

log = logging.getLogger("web")

# No inline scripts or styles, no third-party origins, never inside a frame.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'none'")  # style attributes only: KaTeX positions formula parts with them


class FirstForwardedFor:
    """Render (Cloudflare, then its load balancer) puts the student's real IP first in X-Forwarded-For and its own
    proxies after it; ProxyFix counts from the end, so it would see a proxy. Used for the login rate limits."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        first = environ.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if first:
            environ["REMOTE_ADDR"] = first
        return self.app(environ, start_response)


def create_app(overrides: dict | None = None) -> Flask:
    redact.install()  # passwords, cookies and tokens never reach a log, whatever logs them
    app = Flask(__name__, static_folder=str(config.ROOT / "static"), static_url_path="/static")
    # "web" is Flask's app logger: touching it attaches Flask's stderr handler (with a timestamp), which is what Render
    # shows; INFO so that normal events (sign-ins, scheduled syncs) are visible, not only warnings
    app.logger.setLevel(logging.INFO)
    app.config.update(config.from_env())
    app.config.update(overrides or {})
    if app.config["HOSTED"]:
        crypto.keys()  # fail at start-up, not at the first sign-in, when CREDENTIAL_KEY is missing or malformed
        if app.config["BEHIND_RENDER"]:  # HTTPS from Render's proxy; the client IP is the first forwarded one
            app.wsgi_app = FirstForwardedFor(ProxyFix(app.wsgi_app, x_for=0, x_proto=1))
        else:
            hops = app.config["PROXY_HOPS"]
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)  # real client IP for rate limits

    engine = db.make_engine(app.config["DATABASE_URL"])
    app.extensions["db_engine"] = engine
    app.extensions["db_sessions"] = db.make_session_factory(engine)
    app.teardown_appcontext(db.close_session)

    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = ""  # no "please log in" flash
    login_manager.session_protection = "basic"  # "strong" would log out students whose mobile IP changes

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session().get(User, int(user_id))  # a deleted user is simply signed out
        except ValueError:
            return None

    from web.views import account, ask, auth, dashboard, internal, pages
    for blueprint in (auth.bp, account.bp, pages.bp, dashboard.bp, ask.bp, internal.bp):
        app.register_blueprint(blueprint)

    @app.before_request
    def _host_and_language():
        if request.path != "/healthz" and (request.host or "").rsplit(":", 1)[0].lower() not in app.config["ALLOWED_HOSTS"]:
            abort(400)  # another Host header: DNS rebinding or a misconfigured proxy
        g.lang = i18n.pick(request.args.get("lang") or request.cookies.get("lang"), request.accept_languages)

    @app.after_request
    def _headers(resp):
        if resp.mimetype == "text/html":  # pages only: a PDF opened from /file keeps the browser's own viewer
            resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if app.config["HOSTED"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.args.get("lang") in i18n.LANGS:
            resp.set_cookie("lang", g.lang, max_age=365 * 24 * 3600, samesite="Lax", httponly=True,
                            secure=app.config["SESSION_COOKIE_SECURE"])
        return resp

    def lang_url(code: str) -> str:
        if request.endpoint and request.endpoint != "static":
            return url_for(request.endpoint, **(request.view_args or {}), lang=code)
        return url_for("auth.login", lang=code)

    def course_color(course_id: int) -> str:
        if "colors" not in g:
            g.colors = data.colors(db.session(), current_user.id) if current_user.is_authenticated else {}
        return g.colors.get(course_id, data.COURSE_COLORS[0])

    def sync_pill() -> dict:
        """The student's last sync for the top bar; a page (an error page too) still renders without it."""
        try:
            return dashboard.sync_status(db.session(), current_user.id)
        except Exception:
            log.exception("sync status unavailable")
            return {"state": "none", "message": "", "short": "—"}

    @app.context_processor
    def _template_globals():
        lang = g.get("lang", i18n.DEFAULT)
        return {"t": lambda key, **kw: i18n.t(lang, key, **kw), "lang": lang, "langs": i18n.LANGS,
                "lang_url": lang_url, "app_name": app.config["APP_NAME"], "eclass_url": ECLASS_URL,
                "has_text": lambda key: key in i18n.S or key in base_i18n.S,
                "pl": lambda n, word: base_i18n.plural(lang, n, word), "js_t": base_i18n.js_strings(lang),
                "course_color": course_color, "sync_pill": sync_pill}

    @app.template_filter("web_link")
    def _web_link(url: str | None) -> str:
        """Only http(s) links from eClass content become clickable (never javascript: or data:)."""
        return url if url and urlparse(url).scheme in ("http", "https") else "#"

    @app.template_filter("dt")
    def _dt(value) -> str:
        return base_i18n.short_date(g.get("lang", i18n.DEFAULT), value.astimezone(data.TZ)) if value else "—"

    @app.template_filter("ext")
    def _ext(name: str) -> str:
        return PurePosixPath(name or "").suffix.lstrip(".").upper()[:4] or "FILE"

    @app.template_filter("size")
    def _size(n: int | None) -> str:
        if not n:
            return ""
        for unit in ("B", "KB", "MB"):
            if n < 1024:
                return f"{n:.0f} {unit}"
            n /= 1024
        return f"{n:.1f} GB"

    def error_page(code: int, title_key: str, text_key: str):
        lang = g.get("lang", i18n.DEFAULT)
        return render_template("error.html", code=code, title=i18n.t(lang, title_key),
                               text=i18n.t(lang, text_key)), code

    app.register_error_handler(CSRFError, lambda e: error_page(400, "err.400.title", "web.err.csrf"))
    app.register_error_handler(400, lambda e: error_page(400, "err.400.title", "err.400.text"))
    app.register_error_handler(404, lambda e: error_page(404, "err.404.title", "err.404.text"))
    app.register_error_handler(405, lambda e: error_page(405, "err.405.title", "err.405.text"))
    app.register_error_handler(429, lambda e: error_page(429, "web.err.429.title", "web.login.too_many"))

    @app.errorhandler(500)
    def _server_error(exc):
        log.error("server error on %s", request.path, exc_info=getattr(exc, "original_exception", exc))
        return error_page(500, "err.500.title", "web.err.500.text")

    @app.cli.command("rotate-credentials")
    def rotate_credentials():
        """Re-encrypt stored eClass passwords and sessions with the current CREDENTIAL_KEY."""
        with app.extensions["db_sessions"]() as session:
            stats = crypto.rotate(session)
            session.commit()
        print(f"re-encrypted {stats['passwords']} password(s) and {stats['sessions']} session(s); "
              f"dropped {stats['dropped']} that no key could decrypt")

    @app.get("/healthz")
    @limiter.exempt
    def healthz():
        """Render's health check: the app is up and the database answers."""
        db.session().execute(text("SELECT 1"))
        return jsonify(status="ok")

    return app
