import pytest
from sqlalchemy import event
from app.db.session import engine, SessionLocal


@pytest.fixture
def db():
    """
    Database session fix that allows commits but
    rolls back all changes after each test.
    """
    connection = engine.connect()
    transaction = connection.begin()

    session = SessionLocal(bind=connection)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
