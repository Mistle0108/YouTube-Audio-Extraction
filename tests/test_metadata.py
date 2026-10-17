from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest

import imageio_ffmpeg
from mutagen.id3 import ID3
from PIL import Image

from metadata import TrackMetadata, apply_metadata, normalize_cover


class MetadataTests(unittest.TestCase):
    def test_tags_cover_and_removal_keep_audio_decodable(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "음원.mp3"
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            generated = subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", str(audio)], capture_output=True)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            original = BytesIO()
            Image.new("RGBA", (1900, 950), (10, 100, 200, 160)).save(original, format="PNG")
            cover = normalize_cover(original.getvalue())
            apply_metadata(audio, TrackMetadata(title="한글 제목", artist="가수", album="앨범", year="2026", track="2", genre="Pop", cover=cover))
            tags = ID3(audio)
            self.assertEqual(tags.version, (2, 3, 0))
            for name, value in (("TIT2", "한글 제목"), ("TPE1", "가수"), ("TALB", "앨범"), ("TDRC", "2026"), ("TRCK", "2"), ("TCON", "Pop")):
                self.assertEqual(str(tags[name]), value)
            self.assertEqual(tags.getall("APIC")[0].data, cover)
            with Image.open(BytesIO(cover)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (1600, 800))
            # Setting fields to empty removes prior tags and choosing None removes the cover.
            apply_metadata(audio, TrackMetadata(title="다시 저장"))
            tags = ID3(audio)
            self.assertEqual(tags.getall("APIC"), [])
            self.assertNotIn("TPE1", tags)
            decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(audio), "-f", "null", "-"], capture_output=True)
            self.assertEqual(decoded.returncode, 0, decoded.stderr)

    def test_invalid_year_and_track_are_rejected(self):
        for data in (TrackMetadata(year="202"), TrackMetadata(year="text"), TrackMetadata(track="0"), TrackMetadata(track="1/2")):
            with self.subTest(data=data), self.assertRaises(ValueError):
                data.validate()


if __name__ == "__main__":
    unittest.main()
