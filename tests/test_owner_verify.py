"""Access boundaries for the temporary Render-only diagnostic browser."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from clipdock import hosting, owner_verify as verify
from clipdock import app as application


class OwnerVerificationTests(unittest.TestCase):
    def test_secret_csrf_owner_and_expiry_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(hosting, "HOSTED", True), patch.multiple(
                application, DATA=root, DOWNLOADS=root / "Downloads", STATE=root / "history.json", JOBS={}
            ), patch.multiple(verify, KEY="fixture-" * 8, OWNER=None, EXPIRES=0, ATTEMPTS=0), patch.object(
                verify, "start_browser"
            ) as start, patch.object(verify.threading, "Timer"):
                with TestClient(application.app, base_url="https://testserver") as first, TestClient(
                    application.app, base_url="https://testserver"
                ) as second:
                    first_headers = {"X-ClipDock-Token": first.get("/api/config").json()["token"]}
                    second_headers = {"X-ClipDock-Token": second.get("/api/config").json()["token"]}
                    self.assertEqual(first.get("/owner-verification/frame").status_code, 403)
                    key = {"key": verify.KEY}
                    self.assertEqual(first.post("/owner-verification/unlock", json=key).status_code, 403)
                    self.assertEqual(first.post("/owner-verification/unlock", json={"key": "wrong"}, headers=first_headers).status_code, 403)
                    response = first.post("/owner-verification/unlock", json=key, headers=first_headers)
                    self.assertEqual(response.status_code, 200)
                    self.assertNotIn(verify.KEY, response.text)
                    start.assert_called_once()
                    self.assertEqual(second.post("/owner-verification/unlock", json=key, headers=second_headers).status_code, 403)
                    self.assertEqual(second.get("/owner-verification/frame").status_code, 403)
                    self.assertEqual(first.post("/owner-verification/click", json={"x": 1280, "y": 0}, headers=first_headers).status_code, 422)
                    self.assertEqual(first.post("/owner-verification/text", json={"text": "password@example.com"}, headers=first_headers).status_code, 422)
                    verify.EXPIRES = time.monotonic() - 1
                    self.assertEqual(first.get("/owner-verification/frame").status_code, 403)

    def test_navigation_cannot_reach_accounts_or_arbitrary_sites(self):
        for url in ("https://accounts.google.com/", "http://www.youtube.com/watch?v=test", "https://example.com/", "file:///etc/passwd"):
            with self.subTest(url=url), patch.object(verify, "cdp", return_value={"result": {"value": url}}), patch.object(verify, "stop_browser") as stop:
                with self.assertRaisesRegex(RuntimeError, "account sign-in"):
                    verify.allowed_page()
                stop.assert_called_once()
        for url in (verify.VIDEO, "https://www.google.com/sorry/index?continue=test"):
            with self.subTest(url=url), patch.object(verify, "cdp", return_value={"result": {"value": url}}), patch.object(verify, "stop_browser") as stop:
                verify.allowed_page()
                stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
