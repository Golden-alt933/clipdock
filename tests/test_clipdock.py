import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipdock.cli import main
from clipdock import __version__
from clipdock.paths import data_directory
from clipdock.urls import normalize_url


class UrlTests(unittest.TestCase):
    def test_video_links_are_canonicalized_and_tracking_removed(self):
        expected = ("https://www.youtube.com/watch?v=q6ZqeyEh64A", "YouTube")
        for url in ["https://youtu.be/q6ZqeyEh64A?si=tracking", "https://www.youtube.com/shorts/q6ZqeyEh64A", expected[0] + "&list=playlist"]:
            self.assertEqual(normalize_url(url), expected)
        self.assertEqual(normalize_url("https://www.instagram.com/reels/Chunk8-jurw/?igsh=tracking")[0],
                         "https://www.instagram.com/reel/Chunk8-jurw/")
        self.assertEqual(normalize_url("https://www.pinterest.com/pin/origami--664281013778109217/?x=1")[0],
                         "https://www.pinterest.com/pin/664281013778109217/")

    def test_unsupported_and_misleading_hosts_are_rejected(self):
        for url in ["file:///etc/passwd", "http://127.0.0.1/video", "https://youtube.com.evil.test/watch?v=q6ZqeyEh64A",
                    "https://youtube.com@127.0.0.1/", "https://youtube.com:123/watch?v=q6ZqeyEh64A",
                    "https://youtube.com/playlist?list=abc", "https://instagram.com/profile/", "https://pinterest.com/user/board/"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_url(url)


class PathTests(unittest.TestCase):
    def test_explicit_data_directory_is_resolved(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CLIPDOCK_DATA_DIR":folder}):
            self.assertEqual(data_directory(), Path(folder).resolve())

    def test_linux_obeys_xdg(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_DATA_HOME":folder}, clear=True), patch("sys.platform", "linux"):
            self.assertEqual(data_directory(), Path(folder) / "clipdock")


class CliTests(unittest.TestCase):
    def test_invalid_url_fails_without_starting_a_downloader(self):
        with patch("subprocess.Popen") as spawn, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["download", "https://127.0.0.1/video"]), 2)
            spawn.assert_not_called()

    def test_missing_ffmpeg_gives_actionable_error(self):
        output = io.StringIO()
        with patch("shutil.which", return_value=None), contextlib.redirect_stderr(output):
            self.assertEqual(main(["download", "https://youtu.be/q6ZqeyEh64A"]), 2)
        self.assertIn("clipdock doctor", output.getvalue())

    def test_json_cli_uses_real_worker_protocol(self):
        events = [{"event":"metadata", "title":"Sample"}, {"event":"complete", "path":"sample.mp4"}]
        process = unittest.mock.Mock()
        process.stdout = iter(json.dumps(event) + "\n" for event in events)
        process.wait.return_value = 0
        output = io.StringIO()
        with patch("shutil.which", return_value="installed"), patch("subprocess.Popen", return_value=process), contextlib.redirect_stdout(output):
            self.assertEqual(main(["download", "https://youtu.be/q6ZqeyEh64A", "--format", "mp3", "--audio-bitrate", "256", "--json"]), 0)
        self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()], events)
        sent = json.loads(process.stdin.write.call_args.args[0])
        self.assertEqual(sent["url"], "https://www.youtube.com/watch?v=q6ZqeyEh64A")
        self.assertEqual(sent["audio_bitrate"], "256")

    def test_module_entry_point_and_bundled_assets(self):
        result = subprocess.run([sys.executable, "-m", "clipdock", "--version"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(__version__, result.stdout)
        from importlib.resources import files
        for asset in ["index.html", "app.js", "style.css", "mobile.css", "apollo-sky.webp", "manrope-latin.woff2", "Manrope-OFL.txt"]:
            self.assertTrue(files("clipdock").joinpath("static", asset).is_file())


class ApiTests(unittest.TestCase):
    def test_local_api_queue_file_delivery_and_history(self):
        from fastapi.testclient import TestClient
        from clipdock import app as module
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.multiple(module, DATA=root, DOWNLOADS=root / "Downloads", STATE=root / "history.json", JOBS={}):
                with TestClient(module.app) as client, patch.object(module.POOL, "submit"), patch("shutil.which", return_value="ffmpeg"):
                    self.assertEqual(client.get("/").status_code, 200)
                    self.assertEqual(client.get("/static/style.css").status_code, 200)
                    self.assertEqual(client.get("/api/config", headers={"Host":"evil.test"}).status_code, 400)
                    token = client.get("/api/config").json()["token"]
                    headers = {"X-ClipDock-Token":token}
                    url = "https://youtu.be/q6ZqeyEh64A"
                    self.assertEqual(client.post("/api/jobs", json={"url":url}).status_code, 403)
                    self.assertEqual(client.post("/api/jobs", json={"url":"https://127.0.0.1"}, headers=headers).status_code, 400)
                    self.assertEqual(client.post("/api/jobs", json={"url":url,"format":"exe"}, headers=headers).status_code, 400)
                    self.assertEqual(client.post("/api/jobs", json={"url":url,"format":"mp3","audio_bitrate":"999"}, headers=headers).status_code, 400)
                    audio = client.post("/api/jobs", json={"url":url,"format":"mp3"}, headers=headers)
                    self.assertEqual(audio.status_code, 202)
                    self.assertEqual(audio.json()["audio_bitrate"], "320")
                    source = client.post("/api/jobs", json={"url":url,"format":"audio"}, headers=headers)
                    self.assertEqual(source.status_code, 202)
                    source_id = source.json()["id"]
                    source_folder = root / "Downloads" / source_id
                    source_folder.mkdir()
                    (source_folder / "sample.m4a").write_bytes(b"audio-fixture")
                    module.JOBS[source_id].update(status="complete",filename="sample.m4a")
                    source_file = client.get(f"/api/jobs/{source_id}/file")
                    self.assertEqual(source_file.headers["content-type"], "audio/mp4")
                    created = client.post("/api/jobs", json={"url":url}, headers=headers)
                    self.assertEqual(created.status_code, 202)
                    job_id = created.json()["id"]
                    self.assertEqual(client.get(f"/api/jobs/{job_id}/file").status_code, 404)
                    cancelled = client.post(f"/api/jobs/{job_id}/cancel", json={}, headers=headers)
                    self.assertEqual(cancelled.json()["status"], "cancelled")
                    self.assertTrue((root / "history.json").is_file())
                    job = module.JOBS[job_id]
                    media_folder = root / "Downloads" / job_id
                    media_folder.mkdir()
                    (media_folder / "sample.mp4").write_bytes(b"sample-video")
                    job.update(status="complete", filename="sample.mp4")
                    saved = client.get(f"/api/jobs/{job_id}/file")
                    self.assertEqual(saved.status_code, 200)
                    self.assertEqual(saved.content, b"sample-video")
                    job["filename"] = "../../history.json"
                    self.assertEqual(client.get(f"/api/jobs/{job_id}/file").status_code, 404)
                    job.update(status="downloading", filename="sample.mp4")
                    module.save_state()
                    module.JOBS.clear()
                    module.load_state()
                    self.assertEqual(module.JOBS[job_id]["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
