"""Check atomic database writes and durable duplicate detection."""

import sqlite3

import pytest

from agent_desk.handled import Handled


def test_restart_and_consumer_scope(tmp_path):
    """A saved key survives restart and belongs to one consumer."""
    path = tmp_path / "handled.sqlite"
    store = Handled(path)
    calls = []
    assert store.run("triage", "T-1:triage", lambda connection: calls.append(1))
    assert not store.run("triage", "T-1:triage", lambda connection: calls.append(2))
    store.close()
    store = Handled(path)
    assert not store.run("triage", "T-1:triage", lambda connection: calls.append(3))
    assert store.run("audit", "T-1:triage", lambda connection: calls.append(4))
    assert calls == [1, 4]
    store.close()


def test_atomic_write_and_rollback(tmp_path):
    """A failed handler saves neither its write nor its handled key."""
    path = tmp_path / "handled.sqlite"
    store = Handled(path)
    store.connection.execute("CREATE TABLE effects (value TEXT)")
    observer = sqlite3.connect(path)

    def fail(connection):
        """Write inside the transaction, then fail before commit."""
        connection.execute("INSERT INTO effects VALUES ('failed')")
        assert observer.execute("SELECT * FROM effects").fetchall() == []
        raise RuntimeError("Try again")

    with pytest.raises(RuntimeError):
        store.run("resolver", "T-1:resolve", fail)
    assert observer.execute("SELECT * FROM effects").fetchall() == []
    assert observer.execute("SELECT * FROM handled").fetchall() == []
    assert store.run("resolver", "T-1:resolve", lambda connection: connection.execute("INSERT INTO effects VALUES ('done')"))
    assert observer.execute("SELECT * FROM effects").fetchall() == [("done",)]
    assert observer.execute("SELECT * FROM handled").fetchall() == [("resolver", "T-1:resolve")]
    observer.close()
    store.close()


def test_failed_key_write_rolls_back_effect(tmp_path):
    """Failure to save the key also rolls back the business write."""
    store = Handled(tmp_path / "handled.sqlite")
    store.connection.execute("CREATE TABLE effects (value TEXT)")
    store.connection.execute("CREATE TRIGGER reject_key BEFORE INSERT ON handled BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.run("resolver", "T-1:resolve", lambda connection: connection.execute("INSERT INTO effects VALUES ('lost')"))
    assert store.connection.execute("SELECT * FROM effects").fetchall() == []
    store.close()
