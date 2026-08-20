"""Integration test fixtures — real Postgres (TEST_DATABASE_URL), no mocking of the database
layer. Each test runs inside a SAVEPOINT that's rolled back afterward, so tests never leak
state into each other even though services call `session.commit()` internally.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.dependencies.database import get_db

# Importing app.main transitively imports every service/repository, which in turn imports
# every model module — so Base.metadata is fully populated by the time this line finishes.
# (A bare `import app.models` here would look more direct, but it rebinds the local name `app`
# to the top-level package, clobbering the FastAPI instance imported below — classic Python
# footgun with `import a.b` vs `from a import b`.)
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _disable_rate_limiting():
    # RateLimiterMiddleware tracks hits in-memory, keyed by client IP — every TestClient
    # request across the whole session shares one "testclient" IP and one never-reset window,
    # so a growing suite eventually trips the same 120/min limit a real abusive client would.
    # Tests exercise business logic, not abuse protection, so raise the ceiling for the
    # session rather than let unrelated tests start failing once the suite gets large enough.
    settings.RATE_LIMIT_PER_MINUTE = 1_000_000


@pytest.fixture(scope="session")
def test_engine():
    url = settings.TEST_DATABASE_URL or settings.sqlalchemy_database_url
    engine = create_engine(url, future=True)
    # DROP SCHEMA ... CASCADE resets the test DB regardless of what's left over from a prior
    # run — Postgres resolves the circular-FK drop ordering itself, unlike SQLAlchemy's
    # Python-side topological sort (Base.metadata.drop_all()), which can't sort tables with a
    # genuine FK cycle (rfqs <-> store_returns) even with use_alter declared on the model.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    Session = sessionmaker(bind=connection, future=True)
    session = Session()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, transaction):
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
