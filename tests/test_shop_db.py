"""Check fixed shop rows and safe, repeatable refunds."""

import sqlite3

import pytest

from agent_desk.cli import main
from agent_desk.shop_db import ShopDB, seed


def test_seed_twice(tmp_path):
    """The seed command adds the same rows and keeps existing refunds."""
    path = tmp_path / "shop.sqlite"
    assert main(["seed", "--db-path", str(path)]) == 0
    shop = ShopDB(path)
    shop.issue_refund("O-1", 10, "T-1:refund")
    with sqlite3.connect(path) as connection:
        before = list(connection.iterdump())
    seed(path)
    with sqlite3.connect(path) as connection:
        assert list(connection.iterdump()) == before
    assert shop.lookup_order("O-1") == {
        "id": "O-1", "customer_id": "C-1", "items": [{"name": "Mug", "quantity": 1}],
        "total": 30, "status": "shipped",
    }
    assert shop.shipment_status("O-1")["state"] == "in_transit"
    assert shop.refund_policy("refund")["auto_limit"] == 50


def test_refund_idempotency_and_total(tmp_path):
    """A refund key survives restart and cannot pay twice or change meaning."""
    path = tmp_path / "shop.sqlite"
    seed(path)
    shop = ShopDB(path)
    first = shop.issue_refund("O-1", 20, "T-1:refund")
    assert ShopDB(path).issue_refund("O-1", 20, "T-1:refund") == first
    with pytest.raises(ValueError, match="different refund"):
        shop.issue_refund("O-2", 20, "T-1:refund")
    with pytest.raises(ValueError, match="remaining total"):
        shop.issue_refund("O-1", 11, "T-2:refund")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*), SUM(amount_cents) FROM refunds").fetchone() == (1, 2000)


@pytest.mark.parametrize("amount", [0, -1, float("nan"), float("inf"), 0.001])
def test_bad_amount(tmp_path, amount):
    """Invalid money never changes the database."""
    path = tmp_path / "shop.sqlite"
    seed(path)
    with pytest.raises(ValueError, match="amount"):
        ShopDB(path).issue_refund("O-1", amount, "T-1:refund")


def test_huge_refund_is_rejected(tmp_path):
    """Very large money values give a clear error instead of a decimal failure."""
    path = tmp_path / "shop.sqlite"
    seed(path)
    with pytest.raises(ValueError, match="remaining total"):
        ShopDB(path).issue_refund("O-1", 1e100, "T-1:refund")
