"""Milestone 1: migrations, table rules and the "delete my data" guarantee, on a real Postgres test database."""
from datetime import date, datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

import web
from web import config
from web.models import (Activity, AIUsage, Base, Course, EClassCredential, EClassSession, Enrollment, Material,
                        MaterialPage, Progress, StudyPack, SyncRun, User, UserAssignment)
from tests.web.conftest import TEST_DATABASE_URL, alembic_config

PERSONAL = [EClassCredential, EClassSession, Enrollment, UserAssignment, Progress, SyncRun, AIUsage]


def make_user(db, username="u2410001"):
    user = User(eclass_username=username)
    db.add(user)
    db.commit()
    return user


def rejected(db, *rows):
    """The database refuses these rows; the test goes on from the last commit."""
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def count(db, model, **where):
    return db.scalar(select(func.count()).select_from(model).filter_by(**where))


# ---------------------------------------------------------------- migrations

def test_migrations_run_down_and_up(engine):
    command.downgrade(alembic_config(), "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(alembic_config(), "head")
    assert {t.name for t in Base.metadata.sorted_tables} <= set(inspect(engine).get_table_names())


def test_models_and_migrations_agree(engine):
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


# ---------------------------------------------------------------- table rules

def test_usernames_are_unique_and_normalized(db):
    make_user(db, "u2410001")
    rejected(db, User(eclass_username="u2410001"))
    rejected(db, User(eclass_username="U2410002"))
    rejected(db, User(eclass_username=" u2410003"))
    rejected(db, User(eclass_username=""))


def test_credential_rules(db):
    user = make_user(db)
    rejected(db, EClassCredential(user_id=user.id, autosync_enabled=True))            # autosync needs a password
    rejected(db, EClassCredential(user_id=user.id, encrypted_password="gAAAA-test"))  # password needs key_version
    rejected(db, EClassCredential(user_id=user.id, status="expired"))
    db.add(EClassCredential(user_id=user.id))  # did not opt in: nothing stored
    db.commit()
    credential = db.get(EClassCredential, user.id)
    assert (credential.encrypted_password, credential.autosync_enabled, credential.status) == (None, False, "active")
    credential.encrypted_password, credential.key_version, credential.autosync_enabled = "gAAAA-test", 1, True
    db.commit()


def test_sync_run_values(db):
    user = make_user(db)
    rejected(db, SyncRun(user_id=user.id, trigger="hacker"))
    rejected(db, SyncRun(user_id=user.id, trigger="login", status="maybe"))
    db.add(SyncRun(user_id=user.id, trigger="schedule"))
    db.commit()
    run = db.scalars(select(SyncRun)).one()
    assert (run.status, run.new_items, run.errors, run.finished_at) == ("running", 0, 0, None)


def test_one_enrollment_per_student_and_course(db):
    user = make_user(db)
    db.add(Course(id=2539, name="Calculus 1"))
    db.commit()
    db.add(Enrollment(user_id=user.id, course_id=2539))
    db.commit()
    rejected(db, Enrollment(user_id=user.id, course_id=2539))


# ---------------------------------------------------------------- deletion

def test_every_personal_table_is_deleted_with_its_user():
    for table in Base.metadata.sorted_tables:
        if "user_id" in table.c:
            to_users = [fk for fk in table.c.user_id.foreign_keys if fk.column.table.name == "users"]
            assert to_users and to_users[0].ondelete == "CASCADE", table.name


def test_deleting_a_user_removes_their_data_and_keeps_shared_content(db):
    first, second = make_user(db, "u2410001"), make_user(db, "u2410002")
    db.add(Course(id=2539, name="Calculus 1"))
    db.commit()  # parents first: the models declare no relationships
    db.add_all([Activity(id=701, course_id=2539, type="assign", name="HW 1"),
                Activity(id=702, course_id=2539, type="ubfile", name="Lecture 1")])
    db.commit()
    material = Material(activity_id=702, filename="lecture1.pdf", eclass_url="https://eclass.inha.ac.kr/x/lecture1.pdf")
    db.add(material)
    db.commit()
    soon = datetime.now(timezone.utc) + timedelta(hours=2)
    for user in (first, second):
        db.add_all([EClassCredential(user_id=user.id, encrypted_password="gAAAA-test", key_version=1,
                                     autosync_enabled=True),
                    EClassSession(user_id=user.id, encrypted_cookie="gAAAA-test", key_version=1, expires_at=soon),
                    Enrollment(user_id=user.id, course_id=2539),
                    UserAssignment(user_id=user.id, activity_id=701, grade="9.00 / 10.00"),
                    Progress(user_id=user.id, material_id=material.id),
                    SyncRun(user_id=user.id, trigger="login"),
                    AIUsage(user_id=user.id, day=date.today(), count=3)])
    db.commit()
    db.execute(delete(User).where(User.id == first.id))
    db.commit()
    for model in PERSONAL:
        assert (count(db, model, user_id=first.id), count(db, model, user_id=second.id)) == (0, 1), model.__name__
    assert db.get(Course, 2539) is not None and db.get(Material, material.id) is not None


def test_deleting_a_course_removes_its_content(db):
    db.add(Course(id=2539, name="Calculus 1"))
    db.commit()  # parents first: the models declare no relationships
    db.add(Activity(id=702, course_id=2539, type="ubfile", name="Lecture 1"))
    db.commit()
    material = Material(activity_id=702, filename="l1.pdf", eclass_url="https://eclass.inha.ac.kr/x/l1.pdf")
    db.add(material)
    db.commit()
    db.add_all([MaterialPage(material_id=material.id, page=1, text="Limits"),
                StudyPack(material_id=material.id, sha256="0" * 64, language="uz", provider="gemini", model="m",
                          summary="s", concepts=[], flashcards=[], quiz=[])])
    db.commit()
    db.execute(delete(Course).where(Course.id == 2539))
    db.commit()
    assert [count(db, m) for m in (Activity, Material, MaterialPage, StudyPack)] == [0, 0, 0, 0]


# ---------------------------------------------------------------- search and app

def test_page_text_is_full_text_searchable(db):
    db.add(Course(id=2539, name="Calculus 1"))
    db.commit()  # parents first: the models declare no relationships
    db.add(Activity(id=702, course_id=2539, type="ubfile", name="Lecture 2"))
    db.commit()
    material = Material(activity_id=702, filename="l2.pdf", eclass_url="https://eclass.inha.ac.kr/x/l2.pdf")
    db.add(material)
    db.commit()
    db.add_all([MaterialPage(material_id=material.id, page=1, text="Derivatives measure the rate of change."),
                MaterialPage(material_id=material.id, page=2, text="An integral adds up areas.")])
    db.commit()

    def pages(query):
        return db.scalars(text("SELECT page FROM material_pages WHERE tsv @@ websearch_to_tsquery('english', :q) "
                               "ORDER BY page"), {"q": query}).all()
    assert pages("derivative rate") == [1]  # stemming: derivative ~ Derivatives
    assert pages("integrals") == [2]
    assert pages("pointer") == []


def test_health_check_reaches_the_database(engine):
    app = web.create_app({"DATABASE_URL": TEST_DATABASE_URL, "TESTING": True})
    resp = app.test_client().get("/healthz")
    assert resp.status_code == 200 and resp.get_json() == {"status": "ok"}


def test_config_urls_and_required_settings(monkeypatch):
    assert config.database_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert config.database_url("postgresql://u:p@host/db?sslmode=require").startswith("postgresql+psycopg://")
    monkeypatch.setenv("HOSTED", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="DATABASE_URL"):
        config.database_url()
    with pytest.raises(config.ConfigError, match="SECRET_KEY"):
        config.secret_key()
    monkeypatch.setenv("HOSTED", "0")
    assert config.database_url() == config.LOCAL_DATABASE_URL and len(config.secret_key()) == 64
