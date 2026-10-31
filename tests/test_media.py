"""Exercise yt-dlp's real selection against offline media metadata."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yt_dlp
from clipdock import worker


class MediaTests(unittest.TestCase):
    def run_worker(self, output_format="mp4", bitrate="320", extra=None):
        captured = {}
        original = yt_dlp.YoutubeDL
        with tempfile.TemporaryDirectory() as folder:
            def create(options):
                captured["options"] = options
                downloader = original(options)
                info = {"id":"fixture", "title":"Portrait fixture", "duration":30, "extractor":"fixture", "formats":[
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
            with patch.object(worker.yt_dlp, "YoutubeDL", side_effect=create), patch("shutil.which", return_value="ffmpeg"), contextlib.redirect_stdout(output):
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


if __name__ == "__main__":
    unittest.main()
