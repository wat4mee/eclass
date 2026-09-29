"""Flask extensions, created once and attached to the app in create_app()."""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf import CSRFProtect

csrf = CSRFProtect()  # every POST (forms and fetch) needs the session's CSRF token
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)  # the real client IP (ProxyFix on Render); storage from config
