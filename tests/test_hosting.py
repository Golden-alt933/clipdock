import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from clipdock import hosting


class HostingTests(unittest.TestCase):
    def test_visitors_have_private_queues_tokens_and_files(self):
        from clipdock import app as module
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(hosting, "HOSTED", True), patch.multiple(module, DATA=root, DOWNLOADS=root / "Downloads", STATE=root / "history.json", JOBS={}):
                with TestClient(module.app, base_url="https://testserver") as first, TestClient(module.app, base_url="https://testserver") as second, patch.object(module.POOL, "submit"), patch("shutil.which", return_value="installed"):
                    response = first.get("/api/config")
                    self.assertIn("httponly", response.headers["set-cookie"].lower())
                    self.assertIn("secure", response.headers["set-cookie"].lower())
                    self.assertTrue(response.json()["hosted"])
                    self.assertIsNone(response.json()["downloads"])
                    token1 = response.json()["token"]
                    token2 = second.get("/api/config").json()["token"]
                    self.assertNotEqual(token1, token2)
                    first_headers = {"X-ClipDock-Token":token1}
                    second_headers = {"X-ClipDock-Token":token2}
                    payload = {"url":"https://youtu.be/q6ZqeyEh64A"}
                    self.assertEqual(second.post("/api/jobs", json=payload, headers=first_headers).status_code, 403)
                    response = first.post("/api/jobs", json=payload, headers=first_headers)
                    self.assertEqual(response.status_code, 202)
                    self.assertNotIn("owner", response.json())
                    job_id = response.json()["id"]
                    self.assertEqual(len(first.get("/api/jobs").json()), 1)
                    self.assertEqual(second.get("/api/jobs").json(), [])
                    self.assertEqual(second.post(f"/api/jobs/{job_id}/cancel", json={}, headers=second_headers).status_code, 404)
                    media = root / "Downloads" / job_id
                    media.mkdir()
                    (media / "fixture.mp4").write_bytes(b"video-fixture")
                    job = module.JOBS[job_id]
                    job.update(status="complete", filename="fixture.mp4", finished_at=time.time(), path=str(media / "fixture.mp4"))
                    self.assertEqual(second.get(f"/api/jobs/{job_id}/file").status_code, 404)
                    self.assertEqual(first.get(f"/api/jobs/{job_id}/file").content, b"video-fixture")
                    self.assertNotIn("path", first.get("/api/jobs").json()[0])
                    self.assertEqual(first.post("/api/shutdown", json={}, headers=first_headers).status_code, 404)
                    self.assertEqual(first.post("/api/open-folder", json={}, headers=first_headers).status_code, 404)
                    job["finished_at"] = time.time() - hosting.FILE_TTL - 1
                    self.assertEqual(first.get("/api/jobs").json(), [])
                    self.assertFalse(media.exists())

    def test_transfer_cap_refuses_excess_bytes(self):
        with patch.object(hosting, "_TRANSFER", {"month":"", "bytes":0}), patch.object(hosting, "MONTHLY_BYTES", 100):
            self.assertTrue(hosting.reserve_transfer(60))
            self.assertFalse(hosting.reserve_transfer(41))
            self.assertTrue(hosting.reserve_transfer(40))

    def test_download_rate_is_bounded(self):
        with patch.object(hosting, "_REQUESTS", hosting.defaultdict(hosting.deque)):
            for _ in range(6):
                self.assertTrue(hosting.rate_allowed("fixture-client", "download"))
            self.assertFalse(hosting.rate_allowed("fixture-client", "download"))


if __name__ == "__main__":
    unittest.main()
