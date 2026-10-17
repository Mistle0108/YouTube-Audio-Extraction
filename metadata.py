"""Cover image normalization and MP3 ID3 tags."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TCON, TDRC, TIT2, TPE1, TRCK
from PIL import Image, ImageOps


@dataclass(frozen=True)
class TrackMetadata:
    title: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    track: str = ""
    genre: str = ""
    cover: bytes | None = None

    def validate(self):
        if self.year and (not self.year.isascii() or not self.year.isdigit() or len(self.year) != 4):
            raise ValueError("연도는 네 자리 숫자로 입력해 주세요. 예: 2026")
        if self.track and (not self.track.isascii() or not self.track.isdigit() or int(self.track) < 1):
            raise ValueError("트랙 번호는 1 이상의 숫자로 입력해 주세요.")


def normalize_cover(data: bytes) -> bytes:
    """Use JPEG, preserve aspect ratio, and flatten transparency onto white."""
    with Image.open(BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        output = BytesIO()
        background.save(output, format="JPEG", quality=90)
        return output.getvalue()


def apply_metadata(path: Path, metadata: TrackMetadata):
    metadata.validate()
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    for frame, value in ((TIT2, metadata.title), (TPE1, metadata.artist), (TALB, metadata.album),
                         (TDRC, metadata.year), (TRCK, metadata.track), (TCON, metadata.genre)):
        tags.delall(frame.__name__)
        if value:
            tags.add(frame(encoding=3, text=[value]))
    tags.delall("APIC")
    if metadata.cover:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=metadata.cover))
    tags.save(path, v2_version=3)
