"""Shared setup for the opt-in Kafka tests."""

import os
import uuid

import pytest

from agent_desk.kafka_bus import BrokerUnavailable, KafkaBus, check_broker, create_topics


@pytest.fixture(scope="session", autouse=True)
def bootstrap():
    """Return the broker address. Stop the whole run with ONE message if no broker answers."""
    address = os.environ["AGENT_DESK_KAFKA_BOOTSTRAP"]
    try:
        check_broker(address, timeout_s=5)
    except BrokerUnavailable as exc:
        pytest.exit(str(exc), returncode=2)
    return address


@pytest.fixture
def topic(bootstrap):
    """Make a topic with a fresh name, so old records from earlier runs cannot leak in."""
    name = f"test.{uuid.uuid4().hex[:12]}"
    create_topics(bootstrap, [name])
    return name


@pytest.fixture
def bus(bootstrap):
    """Return a KafkaBus on the real broker."""
    return KafkaBus(bootstrap)
