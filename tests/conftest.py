"""Keep offline tests away from external services."""

import ipaddress
import os
import socket

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip broker tests unless the human supplies a broker address."""
    if not os.environ.get("AGENT_DESK_KAFKA_BOOTSTRAP"):
        for item in items:
            if item.get_closest_marker("kafka"):
                item.add_marker(pytest.mark.skip(reason="Set AGENT_DESK_KAFKA_BOOTSTRAP to run Kafka tests"))


@pytest.fixture(autouse=True)
def offline_sockets(monkeypatch, request):
    """Block external connects and broker connects in offline tests."""
    if request.node.get_closest_marker("kafka") or request.node.get_closest_marker("live"):
        return
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    kafka_port = int(os.environ.get("AGENT_DESK_KAFKA_BOOTSTRAP", "localhost:9092").rsplit(":", 1)[-1])

    def check(address):
        """Allow only a loopback address outside the broker ports."""
        if not isinstance(address, tuple):
            raise OSError("Offline tests block this socket address")
        host, port = address[:2]
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not loopback or port in {9092, kafka_port}:
            raise OSError("Offline tests block external and Kafka connections")

    def connect(sock, address):
        """Check an address before connecting."""
        check(address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        """Check an address before the error-code form of connect."""
        check(address)
        return original_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
