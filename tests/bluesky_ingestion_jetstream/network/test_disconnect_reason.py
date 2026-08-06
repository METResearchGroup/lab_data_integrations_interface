"""Tests for the label attached to a dropped connection.

These branches only run during an outage, which is exactly when the label has to
be right and exactly when it cannot be reproduced by hand.
"""

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, InvalidHandshake
from websockets.frames import Close

from bluesky_ingestion_jetstream.network.connection import disconnect_reason


def close(code: int) -> Close:
    return Close(code, "")


class TestDisconnectReason:
    def test_uses_the_code_the_server_sent(self):
        """1006: no close frame -- a keepalive timeout or a dropped network."""

        assert disconnect_reason(ConnectionClosedError(close(1006), None)) == "close_1006"

    def test_reports_a_clean_server_close(self):
        assert disconnect_reason(ConnectionClosedOK(close(1000), None)) == "close_1000"

    def test_falls_back_to_the_code_we_sent(self):
        """A close we initiated still carries a code worth reporting."""

        assert disconnect_reason(ConnectionClosedError(None, close(1011))) == "close_1011"

    def test_names_the_class_when_there_is_no_close_frame(self):
        assert disconnect_reason(ConnectionClosedError(None, None)) == "ConnectionClosedError"

    def test_names_the_class_for_a_non_websocket_failure(self):
        """OSError covers DNS and TCP failures, where no socket was ever opened."""

        assert disconnect_reason(OSError("connection refused")) == "OSError"

    def test_names_the_class_for_a_handshake_failure(self):
        assert disconnect_reason(InvalidHandshake()) == "InvalidHandshake"

    def test_never_returns_the_message(self):
        """An unbounded label value would multiply the series in Mimir."""

        assert "refused" not in disconnect_reason(OSError("connection refused"))
