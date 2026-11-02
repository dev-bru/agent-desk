"""Save handled keys in the same SQLite transaction as handler writes."""

from collections.abc import Callable
from pathlib import Path
import sqlite3


class Handled:
    """Keep durable keys for each consumer and roll back failed work."""

    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), isolation_level=None)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS handled ("
            "consumer TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
            "PRIMARY KEY (consumer, idempotency_key))"
        )

    def run(self, consumer: str, key: str, handler: Callable[[sqlite3.Connection], None]) -> bool:
        """Run new work atomically; the handler must not commit this connection."""
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if self.connection.execute(
                "SELECT 1 FROM handled WHERE consumer = ? AND idempotency_key = ?", (consumer, key)
            ).fetchone():
                self.connection.rollback()
                return False
            handler(self.connection)
            self.connection.execute("INSERT INTO handled VALUES (?, ?)", (consumer, key))
            self.connection.commit()
            return True
        except BaseException:
            self.connection.rollback()
            raise

    def close(self) -> None:
        """Close the database when this worker stops."""
        self.connection.close()
