"""Keep fictional shop data and refund keys in SQLite."""

from contextlib import closing
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3


def seed(path: str | Path) -> None:
    """Add fixed demo rows without removing orders or refunds."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, items TEXT NOT NULL,
                total_cents INTEGER NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS shipments (
                order_id TEXT PRIMARY KEY, carrier TEXT NOT NULL, state TEXT NOT NULL, eta TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS policies (
                category TEXT PRIMARY KEY, text TEXT NOT NULL, max_days INTEGER NOT NULL,
                auto_limit REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS refunds (
                id INTEGER PRIMARY KEY, order_id TEXT NOT NULL, amount_cents INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE);
        """)
        connection.executemany("INSERT OR IGNORE INTO customers VALUES (?, ?)",
                               [("C-1", "Demo Alex"), ("C-2", "Demo Sam")])
        connection.executemany("INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?)", [
            ("O-1", "C-1", json.dumps([{"name": "Mug", "quantity": 1}]), 3000, "shipped"),
            ("O-2", "C-2", json.dumps([{"name": "Lamp", "quantity": 1}]), 12000, "delivered"),
        ])
        connection.executemany("INSERT OR IGNORE INTO shipments VALUES (?, ?, ?, ?)", [
            ("O-1", "Demo Post", "in_transit", "2026-11-05"),
            ("O-2", "Demo Post", "delivered", "2026-11-01"),
        ])
        connection.executemany("INSERT OR IGNORE INTO policies VALUES (?, ?, ?, ?)", [
            (category, "Refunds are allowed within 30 days. Refunds above 50 need approval.", 30, 50.0)
            for category in ("refund", "order_status", "shipping", "product", "other")
        ])


class ShopDB:
    """Read shop rows and issue refunds in one database transaction."""

    def __init__(self, path: str | Path):
        """Keep the path to a seeded shop database."""
        self.path = Path(path)

    def _row(self, table: str, field: str, value: str) -> dict:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(f"SELECT * FROM {table} WHERE {field} = ?", (value,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown {field} '{value}'; use a seeded {table} id")
        return dict(row)

    def lookup_order(self, order_id: str) -> dict:
        """Return an order with its items and total."""
        row = self._row("orders", "id", order_id)
        row["items"] = json.loads(row["items"])
        row["total"] = row.pop("total_cents") / 100
        return row

    def shipment_status(self, order_id: str) -> dict:
        """Return the carrier, state, and arrival date for an order."""
        return self._row("shipments", "order_id", order_id)

    def refund_policy(self, category: str) -> dict:
        """Return the refund rules for a ticket category."""
        return self._row("policies", "category", category)

    def issue_refund(self, order_id: str, amount: float, idempotency_key: str) -> dict:
        """Refund at most the order total and reuse a matching refund key."""
        try:
            money = Decimal(str(amount))
        except InvalidOperation:
            raise ValueError("amount must be a positive number of cents") from None
        if not money.is_finite() or money <= 0 or money * 100 != (money * 100).to_integral_value():
            raise ValueError("amount must be positive, finite, and have at most two decimal places")
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        cents = int(money * 100)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT id, order_id, amount_cents FROM refunds WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if previous:
                if previous[1:] != (order_id, cents):
                    raise ValueError("idempotency_key already belongs to a different refund")
                return {"refund_id": previous[0], "order_id": order_id, "amount": cents / 100}
            order = connection.execute("SELECT total_cents FROM orders WHERE id = ?", (order_id,)).fetchone()
            if order is None:
                raise ValueError(f"Unknown order_id '{order_id}'; use a seeded orders id")
            refunded = connection.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM refunds WHERE order_id = ?", (order_id,)
            ).fetchone()[0]
            if cents > order[0] - refunded:
                raise ValueError(f"amount exceeds the remaining total for '{order_id}'")
            cursor = connection.execute(
                "INSERT INTO refunds (order_id, amount_cents, idempotency_key) VALUES (?, ?, ?)",
                (order_id, cents, idempotency_key),
            )
            return {"refund_id": cursor.lastrowid, "order_id": order_id, "amount": cents / 100}
