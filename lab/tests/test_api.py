"""Endpoint behavior tests; the database is mocked, not a Compose integration test."""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from hello import server
import pymysql


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.client = server.test_client()

    @patch("hello.pymysql.connect", side_effect=pymysql.OperationalError("unavailable"))
    def test_database_outage_does_not_break_liveness(self, connect):
        self.assertEqual(self.client.get("/live").status_code, 200)
        connect.assert_not_called()
        with patch.dict("os.environ", {"LAB_DB_PASSWORD": "test"}):
            response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["reason"], "database_query_failed")

    @patch("hello.time.sleep")
    @patch("hello.ready", return_value=({"status": "ready"}, 200))
    def test_delayed_route_preserves_readiness_behavior(self, ready, sleep):
        response = self.client.get("/slow-ready")
        self.assertEqual(response.status_code, 200)
        sleep.assert_called_once_with(3)
        ready.assert_called_once_with()
        sleep.reset_mock()
        self.assertEqual(self.client.get("/live").status_code, 200)
        sleep.assert_not_called()

    def test_ready_requires_expected_data_and_closes_connection(self):
        for rows, expected in [([("Lab post #1",), ("Lab post #2",)], 200), ([], 503)]:
            with self.subTest(rows=rows):
                connection = MagicMock()
                cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
                cursor.fetchall.return_value = rows
                with patch("hello.pymysql.connect", return_value=connection), patch.dict(
                    "os.environ", {"LAB_DB_PASSWORD": "test"}
                ):
                    response = self.client.get("/ready")
                self.assertEqual(response.status_code, expected)
                cursor.execute.assert_called_once_with("SELECT title FROM blog ORDER BY id")
                connection.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
