"""Pages of the hosted site; T() gives a text in the visitor's language."""
from flask import g

from web import i18n


def T(key: str, **kw) -> str:
    return i18n.t(g.get("lang", i18n.DEFAULT), key, **kw)
