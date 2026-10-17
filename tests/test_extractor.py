import math
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import imageio_ffmpeg
from extractor import Cancelled, extract_mp3, save_unique, validate_url


class ExtractorTests(unittest.TestCase):
    def test_only_youtube_video_urls(self):
        for url in ("https://youtu.be/BaW_jenozKc", "https://www.youtube.com/watch?v=BaW_jenozKc&list=123", "https://www.youtube.com/shorts/abc"):
            self.assertEqual(validate_url(url), url)
        for url in ("", "file:///C:/test", "https://youtube.com.evil.test/watch?v=abc", "https://youtube.com/playlist?list=abc", "https://example.com/video", "https://youtube.com/@channel"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_existing_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source"
            source.write_bytes(b"new")
            (folder / "한글 제목.mp3").write_bytes(b"original")
            output = save_unique(source, folder, "한글 제목")
            self.assertEqual(output.name, "한글 제목 (1).mp3")
            self.assertEqual((folder / "한글 제목.mp3").read_bytes(), b"original")
            self.assertEqual(output.read_bytes(), b"new")

    def test_actual_conversion_and_temporary_cleanup(self):
        # Replace only network download; use the production conversion/save path.
        class DownloadFixture:
            def __init__(self, options):
                self.source = Path(options["outtmpl"].replace("%(ext)s", "wav"))

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def extract_info(self, url, download):
                with wave.open(str(self.source), "wb") as output:
                    output.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
                    output.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(i * 2 * math.pi * 440 / 22050))) for i in range(22050)))
                return {"title": "테스트 음원", "id": "fixture"}

            def prepare_filename(self, info):
                return str(self.source)

        with tempfile.TemporaryDirectory() as directory, patch("extractor.yt_dlp.YoutubeDL", DownloadFixture):
            folder = Path(directory) / "한글 저장 폴더"
            output = extract_mp3("https://youtu.be/BaW_jenozKc", folder, lambda *args: None, threading.Event())
            self.assertGreater(output.stat().st_size, 1000)
            decoded = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True)
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            self.assertEqual(list(folder.iterdir()), [output])

    def test_cancel_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(Cancelled):
                extract_mp3("https://youtu.be/BaW_jenozKc", Path(directory), lambda *args: None, cancel)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
