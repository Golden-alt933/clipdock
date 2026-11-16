"""Exercise yt-dlp's real selection against offline media metadata."""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yt_dlp
from clipdock import worker


class MediaTests(unittest.TestCase):
    def test_instagram_browser_transport_is_available(self):
        with yt_dlp.YoutubeDL({"quiet": True}) as downloader:
            extractor = downloader.get_info_extractor("Instagram")
            self.assertTrue(
                extractor._can_impersonate,
                "Instagram's public API path needs yt-dlp's curl-cffi extra",
            )

    def run_worker(self, output_format="mp4", bitrate="320", extra=None, formats=None):
        captured = {"converted": []}
        original = yt_dlp.YoutubeDL
        with tempfile.TemporaryDirectory() as folder:
            def create(options):
                captured["options"] = options
                downloader = original(options)
                info = {"id":"fixture", "title":"Portrait fixture", "duration":30, "extractor":"fixture", "formats":formats or [
                    {"format_id":"audio", "url":"https://example.com/audio.m4a", "ext":"m4a", "vcodec":"none", "acodec":"aac", "abr":128},
                    {"format_id":"portrait", "url":"https://example.com/video.mp4", "ext":"mp4", "vcodec":"h264", "acodec":"none", "width":720, "height":1280},
                ]}
                downloader.extract_info = lambda *args, **kwargs: info
                def process(selected):
                    captured["selected"] = selected
                    extension = "m4a" if output_format == "audio" else output_format
                    path = Path(folder) / ("fixture." + extension)
                    path.write_bytes(b"media-fixture")
                    for hook in options["post_hooks"]:
                        hook(str(path))
                downloader.process_info = process
                return downloader

            output = io.StringIO()
            with patch.object(worker.yt_dlp, "YoutubeDL", side_effect=create), patch("shutil.which", return_value="ffmpeg"), \
                    patch.object(worker, "make_editable", side_effect=lambda path: captured["converted"].append(path.name)), \
                    contextlib.redirect_stdout(output):
                worker.run({"mode":"download", "url":"https://example.com/video", "folder":folder,
                            "format":output_format, "quality":"1080", "audio_bitrate":bitrate, **(extra or {})})
            captured["events"] = [json.loads(line) for line in output.getvalue().splitlines()]
        return captured

    def test_portrait_reel_is_not_excluded_by_1080_preference(self):
        result = self.run_worker()
        self.assertEqual(result["selected"]["width"], 720)
        self.assertEqual(result["selected"]["height"], 1280)
        self.assertEqual(result["events"][-1]["event"], "complete")

    def test_mp3_bitrate_choices_reach_encoder_and_have_distinct_filenames(self):
        for bitrate in ("128", "192", "256", "320"):
            with self.subTest(bitrate=bitrate):
                result = self.run_worker("mp3", bitrate)
                processor = result["options"]["postprocessors"][0]
                self.assertEqual(processor["preferredquality"], bitrate)
                self.assertEqual(processor["preferredcodec"], "mp3")
                self.assertIn(f"[{bitrate}kbps]", result["options"]["outtmpl"]["default"])

    def test_source_audio_accepts_native_extension_without_mp3_conversion(self):
        result = self.run_worker("audio")
        self.assertEqual(result["options"]["postprocessors"][0]["preferredcodec"], "best")
        self.assertNotIn("preferredquality", result["options"]["postprocessors"][0])
        self.assertEqual(result["events"][-1]["filename"], "fixture.m4a")

    def test_hosted_duration_limit_prevents_download(self):
        with self.assertRaisesRegex(ValueError, "10 minutes"):
            self.run_worker(extra={"max_duration":10})

    def test_hosted_streaming_limit_counts_separate_audio_and_video(self):
        result = self.run_worker(extra={"max_bytes":100})
        progress = result["options"]["progress_hooks"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            progress({"status":"downloading", "filename":"video", "downloaded_bytes":60})
            with self.assertRaisesRegex(ValueError, "100 MB"):
                progress({"status":"downloading", "filename":"audio", "downloaded_bytes":60})

    def test_h264_is_preferred_over_vp9_at_the_same_resolution(self):
        result = self.run_worker(formats=[
            {"format_id":"audio", "url":"https://example.com/a.m4a", "ext":"m4a", "vcodec":"none", "acodec":"aac", "abr":128},
            {"format_id":"vp9", "url":"https://example.com/v9.mp4", "ext":"mp4", "vcodec":"vp09.00.40.08", "acodec":"none",
             "width":1080, "height":1080, "tbr":900},
            {"format_id":"avc", "url":"https://example.com/avc.mp4", "ext":"mp4", "vcodec":"avc1.640028", "acodec":"none",
             "width":1080, "height":1080, "tbr":800},
        ])
        self.assertEqual(result["selected"]["format_id"], "avc+audio")

    def test_mp4_is_checked_for_editor_compatibility_unless_kept(self):
        self.assertEqual(self.run_worker()["converted"], ["fixture.mp4"])
        self.assertEqual(self.run_worker(extra={"editable":False})["converted"], [])
        self.assertEqual(self.run_worker("mp3")["converted"], [])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs FFmpeg")
class EditableConversionTests(unittest.TestCase):
    def make_clip(self, folder, video, audio):
        path = Path(folder) / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
                        "-f", "lavfi", "-i", "sine=duration=1", "-c:v", video, "-pix_fmt", "yuv420p",
                        "-c:a", audio, "-shortest", str(path)], check=True)
        return path

    def test_vp9_and_opus_become_h264_and_aac(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_clip(folder, "libvpx-vp9", "libopus")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertTrue(worker.make_editable(path))
            self.assertEqual(worker.probe_streams(path), ("h264", "yuv420p", "aac"))
            self.assertIn('"converting"', output.getvalue())
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["clip.mp4"])

    def test_h264_and_aac_are_left_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_clip(folder, "libx264", "aac")
            before = path.read_bytes()
            self.assertFalse(worker.make_editable(path))
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()


class YouTubeProxyTests(unittest.TestCase):
    def test_only_youtube_uses_the_proxy(self):
        with patch.dict("os.environ", {"CLIPDOCK_YOUTUBE_PROXY": "socks5://proxy.example:1080"}):
            self.assertEqual(worker.youtube_proxy("https://www.youtube.com/watch?v=jNQXAC9IVRw"),
                             "socks5://proxy.example:1080")
            self.assertIsNone(worker.youtube_proxy("https://www.instagram.com/reel/abc/"))
            self.assertIsNone(worker.youtube_proxy("https://pin.it/abc"))

    def test_no_proxy_configured(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(worker.youtube_proxy("https://www.youtube.com/watch?v=jNQXAC9IVRw"))

    def test_local_proxy_that_is_down_falls_back_to_direct(self):
        import socket
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        with patch.dict("os.environ", {"CLIPDOCK_YOUTUBE_PROXY": f"socks5://127.0.0.1:{free_port}"}):
            self.assertIsNone(worker.youtube_proxy("https://www.youtube.com/watch?v=jNQXAC9IVRw"))

    def test_local_proxy_that_is_listening_is_used(self):
        import socket
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            proxy = f"socks5://127.0.0.1:{server.getsockname()[1]}"
            with patch.dict("os.environ", {"CLIPDOCK_YOUTUBE_PROXY": proxy}):
                self.assertEqual(worker.youtube_proxy("https://www.youtube.com/watch?v=jNQXAC9IVRw"), proxy)


class YouTubeCookieTests(unittest.TestCase):
    def test_cookies_used_only_for_youtube_and_copied_to_writable_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "cookies.txt"
            source.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            with patch.dict("os.environ", {"CLIPDOCK_YOUTUBE_COOKIES": str(source), "CLIPDOCK_YOUTUBE_PROXY": ""}):
                options = worker.youtube_options("https://www.youtube.com/watch?v=jNQXAC9IVRw")
                self.assertNotEqual(options["cookiefile"], str(source))
                self.assertEqual(Path(options["cookiefile"]).read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
                self.assertNotIn("proxy", options)
                self.assertEqual(worker.youtube_options("https://www.instagram.com/reel/abc/"), {})

    def test_missing_cookie_file_falls_back_to_proxy(self):
        with patch.dict("os.environ", {"CLIPDOCK_YOUTUBE_COOKIES": "/nonexistent/cookies.txt",
                                       "CLIPDOCK_YOUTUBE_PROXY": "socks5://proxy.example:1080"}):
            self.assertEqual(worker.youtube_options("https://www.youtube.com/watch?v=jNQXAC9IVRw"),
                             {"proxy": "socks5://proxy.example:1080"})
