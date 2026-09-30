"""Supported source-video providers for URL ingestion.

A provider (1) recognises and canonicalises its URLs, (2) checks that the
video is publicly accessible before a lecture is created, and (3) fetches the
audio in the worker. Only explicitly supported platforms are accepted; this is
not a general URL downloader.

YouTube: availability is checked with YouTube's public oEmbed endpoint. Audio
is fetched with yt-dlp, audio-only, anonymously, and without any attempt to get
around sign-in, age, region or DRM restrictions: such videos fail with a clear
reason. Users must confirm they have the right to process the video.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import httpx

from app.workers.lifecycle import ProcessingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceRef:
    provider: str
    source_id: str
    canonical_url: str

    @property
    def fingerprint(self) -> str:
        return f"{self.provider}:{self.source_id}"


@dataclass(frozen=True)
class SourceInfo:
    title: str | None
    author: str | None


class SourceProvider(Protocol):
    name: str

    def parse(self, url: str) -> SourceRef | None: ...

    async def check_access(self, ref: SourceRef, http: httpx.AsyncClient) -> SourceInfo: ...

    async def fetch_audio(self, ref: SourceRef, directory: Path, *, max_bytes: int, max_duration_seconds: int) -> Path: ...


_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}


class YouTubeProvider:
    name = "youtube"

    def parse(self, url: str) -> SourceRef | None:
        try:
            parsed = urlparse(url.strip())
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https"):
            return None
        host = (parsed.hostname or "").lower()
        video_id = None
        if host == "youtu.be":
            video_id = parsed.path.lstrip("/").split("/")[0]
        elif host in _YOUTUBE_HOSTS:
            if parsed.path == "/watch":
                video_id = (parse_qs(parsed.query).get("v") or [None])[0]
            else:
                match = re.match(r"^/(shorts|live|embed)/([^/?#]+)", parsed.path)
                video_id = match.group(2) if match else None
        if not video_id or not _YOUTUBE_ID.match(video_id):
            return None
        return SourceRef("youtube", video_id, f"https://www.youtube.com/watch?v={video_id}")

    async def check_access(self, ref: SourceRef, http: httpx.AsyncClient) -> SourceInfo:
        try:
            response = await http.get(
                "https://www.youtube.com/oembed", params={"url": ref.canonical_url, "format": "json"}, timeout=10.0
            )
        except httpx.HTTPError as exc:
            raise ProcessingError(
                "source_check_failed", "We couldn't reach YouTube to check this video. Please try again.", retryable=True
            ) from exc
        if response.status_code == 200:
            data = response.json()
            return SourceInfo(title=data.get("title"), author=data.get("author_name"))
        if response.status_code in (401, 403):
            # oEmbed also answers 401 for public videos whose owner disabled embedding,
            # so it can't tell "private" from "not embeddable". Ask the watch page itself
            # (metadata only, no download) before deciding.
            return await asyncio.to_thread(self._lookup_metadata, ref)
        if response.status_code in (400, 404):
            raise ProcessingError("source_not_found", "This video doesn't exist or is no longer available.")
        raise ProcessingError(
            "source_check_failed", "YouTube didn't respond as expected. Please try again.", retryable=True,
            details={"status": response.status_code},
        )

    def _lookup_metadata(self, ref: SourceRef) -> SourceInfo:
        import yt_dlp  # imported lazily: only needed for this fallback and the worker

        options = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "socket_timeout": 15, "cachedir": False}
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(ref.canonical_url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise _restriction_error(str(exc)) from None
        if not info:
            raise ProcessingError("source_not_found", "This video doesn't exist or is no longer available.")
        return SourceInfo(title=info.get("title"), author=info.get("uploader") or info.get("channel"))

    async def fetch_audio(self, ref: SourceRef, directory: Path, *, max_bytes: int, max_duration_seconds: int) -> Path:
        return await asyncio.to_thread(self._download, ref, directory, max_bytes, max_duration_seconds)

    def _download(self, ref: SourceRef, directory: Path, max_bytes: int, max_duration_seconds: int) -> Path:
        import yt_dlp  # imported lazily: only the worker needs it

        def reject_long(info, *, incomplete):
            duration = info.get("duration")
            if duration and duration > max_duration_seconds:
                return "too long"
            if info.get("is_live"):
                return "live"
            return None

        options = {
            "format": "bestaudio/best",
            "outtmpl": str(directory / "source.%(ext)s"),
            "noplaylist": True,
            "max_filesize": max_bytes,
            "match_filter": reject_long,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 3,
            "cachedir": False,
            "restrictfilenames": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(ref.canonical_url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            text = str(exc)
            retryable = any(marker in text for marker in ("timed out", "HTTP Error 5", "Connection reset", "Temporary failure"))
            raise ProcessingError(
                "source_download_failed",
                "The video's audio couldn't be downloaded. It may be restricted or temporarily unavailable.",
                retryable=retryable,
                details={"provider_error": text[-500:]},
            ) from None

        if info is None or not info.get("requested_downloads"):
            if info and info.get("duration") and info["duration"] > max_duration_seconds:
                raise ProcessingError("media_too_long", f"This video is longer than the {max_duration_seconds / 3600:g}-hour limit.")
            raise ProcessingError(
                "source_download_failed", "This video can't be processed (it may be live or too large)."
            )
        files = sorted(directory.glob("source.*"))
        if not files:
            raise ProcessingError("source_download_failed", "The video's audio couldn't be downloaded.")
        return files[0]


_RESTRICTIONS = (
    ("private video", "source_private", "This video is private, so it can't be processed."),
    ("members-only", "source_restricted", "This video is for channel members only, so it can't be processed."),
    ("confirm your age", "source_restricted", "This video is age-restricted and requires sign-in, so it can't be processed."),
    ("not a bot", "source_blocked", "YouTube is asking for sign-in verification before allowing this video's audio to be fetched. Try again later."),
    ("not available in your country", "source_restricted", "This video isn't available in this server's region."),
    ("copyright", "source_restricted", "This video is blocked for copyright reasons."),
    ("live event", "source_restricted", "This is a live stream that hasn't ended, so it can't be processed yet."),
    ("video unavailable", "source_not_found", "This video doesn't exist or is no longer available."),
)


def _restriction_error(provider_message: str) -> ProcessingError:
    """Turn yt-dlp's failure text into a specific, user-facing reason."""
    lowered = provider_message.lower()
    for marker, code, message in _RESTRICTIONS:
        if marker in lowered:
            return ProcessingError(code, message, details={"provider_error": provider_message[-300:]})
    return ProcessingError(
        "source_restricted",
        "YouTube wouldn't let this video be accessed, so it can't be processed.",
        details={"provider_error": provider_message[-300:]},
    )


PROVIDERS: list[SourceProvider] = [YouTubeProvider()]


def resolve_source(url: str) -> tuple[SourceProvider, SourceRef] | None:
    for provider in PROVIDERS:
        ref = provider.parse(url)
        if ref:
            return provider, ref
    return None


def provider_named(name: str) -> SourceProvider:
    return next(provider for provider in PROVIDERS if provider.name == name)
