from getsinapi.api import main as api


class FakeCursor:
    def fetchall(self):
        return [{"value": 1}]


class TrackingConnection:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, parameters=()):
        return FakeCursor()

    def close(self):
        self.closed = True


def test_rows_closes_sqlite_connection_after_query(monkeypatch):
    connection = TrackingConnection()
    monkeypatch.setattr(api, "_connect", lambda: connection)

    assert api._rows("SELECT 1") == [{"value": 1}]
    assert connection.closed is True
