"""eClass (Moodle) login and a polite, self-healing HTTP client."""
import os
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from eclass.config import ECLASS_MIN_INTERVAL as MIN_INTERVAL, ECLASS_TIMEOUT, ECLASS_URL as BASE_URL

USER_AGENT = "Mozilla/5.0 (eClass Companion; personal use)"


class EClassError(RuntimeError):
    """Talking to eClass failed. `code` selects the explanation the dashboard shows (i18n "sync.err.<code>").

    Messages name the page path only: never a password, cookie or full request.
    """
    code = "other"


class ConfigError(EClassError):
    code = "config"          # ECLASS_USER / ECLASS_PASS missing in .env


class LoginError(EClassError):
    code = "login"           # eClass rejected the username or password


class SessionExpired(LoginError):
    code = "session"         # still sent to the login page after logging in again


class NetworkError(EClassError):
    code = "network"         # no connection: offline, DNS failure, connection refused or reset


class EClassTimeout(NetworkError):
    code = "timeout"         # eClass did not answer within ECLASS_TIMEOUT seconds


class ServerError(EClassError):
    code = "server"          # HTTP 5xx: eClass itself is failing


class PageError(EClassError):
    code = "page"            # HTTP 4xx or a page without the expected structure (layout changed?)


def _is_login_url(url):
    path = urlparse(url).path
    return path.startswith("/login") or path == "/login.php"


def _checked(resp):
    """The response itself, or the matching EClassError for an HTTP error status."""
    if resp.status_code >= 500:
        raise ServerError(f"HTTP {resp.status_code}: {urlparse(resp.url).path}")
    if resp.status_code >= 400:
        raise PageError(f"HTTP {resp.status_code}: {urlparse(resp.url).path}")
    return resp


def _bounced_to_login(resp):
    if _is_login_url(resp.url):
        return True
    location = resp.headers.get("Location") if resp.is_redirect else None
    return bool(location) and _is_login_url(urljoin(resp.url, location))


class EClassClient:
    """requests.Session wrapper: rate limiting + re-login on session expiry."""

    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self._user = os.getenv("ECLASS_USER")
        self._pass = os.getenv("ECLASS_PASS")
        if not self._user or not self._pass:
            raise ConfigError("ECLASS_USER / ECLASS_PASS not set in .env")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last_request = 0.0
        self.request_count = 0

    def url(self, path):
        return urljoin(self.base_url, path)

    def _raw(self, method, url, **kwargs):
        wait = MIN_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        kwargs.setdefault("timeout", ECLASS_TIMEOUT)
        try:
            return self.session.request(method, url, **kwargs)
        except requests.Timeout:
            raise EClassTimeout(f"no answer within {kwargs['timeout']} s: {urlparse(url).path}") from None
        except requests.ConnectionError as exc:
            raise NetworkError(f"{type(exc).__name__}: {urlparse(url).path}") from None
        finally:
            self._last_request = time.monotonic()
            self.request_count += 1

    def login(self):
        resp = _checked(self._raw("GET", self.url("/login.php")))
        soup = BeautifulSoup(resp.text, "html.parser")
        form = None
        for f in soup.find_all("form"):
            if f.find("input", attrs={"name": "password"}):
                form = f
                break
        if form is None:
            raise PageError("login form not found on /login.php")
        data = {
            inp["name"]: inp.get("value", "")
            for inp in form.find_all("input", attrs={"type": "hidden"})
            if inp.get("name")
        }
        # Stock Moodle sends a hidden "logintoken"; the Coursemos /login.php form
        # has none. Whatever hidden fields exist are forwarded as-is.
        data["username"] = self._user
        data["password"] = self._pass
        action = urljoin(resp.url, form.get("action") or "/login/index.php")

        resp = _checked(self._raw("POST", action, data=data))
        if _is_login_url(resp.url) or "login/logout.php" not in resp.text:
            raise LoginError("login failed (redirected back to login page)")
        return True

    def request(self, method, path, **kwargs):
        """Request; if bounced to the login page, re-login once and retry."""
        url = self.url(path)
        resp = self._raw(method, url, **kwargs)
        if _bounced_to_login(resp) and not _is_login_url(url):
            resp.close()
            self.login()
            resp = self._raw(method, url, **kwargs)
            if _bounced_to_login(resp):
                raise SessionExpired(f"still redirected to login after re-login: {path}")
        return _checked(resp)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def soup(self, path):
        return BeautifulSoup(self.get(path).text, "html.parser")
