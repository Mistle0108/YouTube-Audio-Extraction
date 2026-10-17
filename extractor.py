"""YouTube download and MP3 conversion, independent of the window."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
import yt_dlp
from yt_dlp.utils import sanitize_filename
from metadata import normalize_cover


class Cancelled(Exception):
    pass


def validate_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    valid_host = host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}
    parts = parsed.path.strip("/").split("/")
    video = (host.endswith("youtu.be") and len(parts) == 1 and bool(parts[0])) or (
        not host.endswith("youtu.be") and (
            (parsed.path == "/watch" and bool(parse_qs(parsed.query).get("v", [""])[0]))
            or (len(parts) == 2 and parts[0] in {"shorts", "live", "embed"} and bool(parts[1]))
        )
    )
    if parsed.scheme not in {"http", "https"} or not valid_host or not video or parsed.username or parsed.password:
        raise ValueError("유튜브 영상 링크를 입력해 주세요.")
    return value


def node_path() -> str | None:
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "tools" / "node.exe"
    return str(bundled) if bundled.is_file() else shutil.which("node")


def save_unique(source: Path, folder: Path, title: str) -> Path:
    """Exclusive creation prevents overwriting files, including concurrent saves."""
    name = sanitize_filename(title, restricted=False).strip(" .")[:140].rstrip(" .") or "audio"
    for index in range(10000):
        suffix = f" ({index})" if index else ""
        target = folder / f"{name}{suffix}.mp3"
        try:
            output = target.open("xb")
        except FileExistsError:
            continue
        try:
            with output, source.open("rb") as data:
                shutil.copyfileobj(data, output)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
    raise OSError("같은 이름의 파일이 너무 많습니다. 다른 저장 폴더를 선택해 주세요.")


class QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def extract_mp3(url: str, folder: Path, emit, cancel: threading.Event) -> Path:
    url = validate_url(url)
    if not folder.is_absolute():
        raise ValueError("저장 폴더는 전체 경로로 지정해 주세요.")
    folder.mkdir(parents=True, exist_ok=True)

    def check_cancel():
        if cancel.is_set():
            raise Cancelled()

    def progress(data):
        check_cancel()
        if data["status"] == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            percent = min(85, data.get("downloaded_bytes", 0) / total * 85) if total else None
            emit("progress", (percent, "음원을 다운로드하고 있습니다…"))

    def filter_video(info, *, incomplete=False):
        check_cancel()
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            return "진행 중이거나 예정된 라이브 방송은 추출할 수 없습니다."
        return None

    check_cancel()
    # Temporary files stay on the selected drive and are removed on success/failure.
    with tempfile.TemporaryDirectory(prefix=".youtube-mp3-", dir=folder) as temporary:
        work = Path(temporary)
        runtime = node_path()
        options = {
            "format": "bestaudio/best",
            "outtmpl": str(work / "source.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietLogger(),
            "progress_hooks": [progress],
            "match_filter": filter_video,
            "socket_timeout": 20,
            "retries": 3,
            "fragment_retries": 3,
            "js_runtimes": {"node": {"path": runtime}} if runtime else {},
        }
        emit("progress", (None, "영상 정보를 확인하고 있습니다…"))
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            if not info:
                raise ValueError("진행 중이거나 예정된 라이브 방송은 추출할 수 없습니다.")
            source = Path(downloader.prepare_filename(info))
            thumbnail = None
            if info.get("thumbnail"):
                check_cancel()
                emit("progress", (None, "앨범 커버용 썸네일을 가져오고 있습니다…"))
                try:
                    with downloader.urlopen(info["thumbnail"]) as response:
                        thumbnail = normalize_cover(response.read())
                except Exception:
                    # Keep the extraction usable; the editor asks for a cover choice before saving.
                    thumbnail = None
            emit("metadata", {"title": info.get("title") or "", "artist": info.get("artist") or "",
                              "album": info.get("album") or "", "year": info.get("release_year") or "",
                              "track": info.get("track_number") or "", "genre": info.get("genre") or "",
                              "thumbnail": thumbnail})
        check_cancel()
        emit("progress", (None, "MP3로 변환하고 있습니다…"))
        converted = work / "result.mp3"
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-i", str(source), "-vn", "-codec:a", "libmp3lame", "-q:a", "2",
                   "-metadata", f"title={info.get('title', 'audio')}", "-id3v2_version", "3", str(converted)]
        with (work / "ffmpeg-error.txt").open("wb") as error_log:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=error_log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                while process.poll() is None:
                    if cancel.wait(0.15):
                        raise Cancelled()
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
        if process.returncode:
            raise RuntimeError("MP3 변환에 실패했습니다. 저장 공간과 원본 영상을 확인해 주세요.")
        check_cancel()
        emit("progress", (95, "MP3 추출을 마무리하고 있습니다…"))
        return save_unique(converted, folder, info.get("title") or info.get("id") or "audio")
