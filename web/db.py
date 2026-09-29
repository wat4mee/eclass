"""Database engine and per-request sessions (SQLAlchemy 2). Neon's pooled connection string works as DATABASE_URL."""
from flask import current_app, g
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    # pool_pre_ping: Neon suspends idle databases and drops their connections; test each one before use.
    # pool_recycle: never reuse a connection older than 5 minutes.
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def session() -> Session:
    """The database session of the current request; closed when the request ends."""
    if "db" not in g:
        g.db = current_app.extensions["db_sessions"]()
    return g.db


def close_session(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
