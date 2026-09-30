"""YouTubeProvider.check_access: oEmbed first, yt-dlp metadata lookup when oEmbed says 401/403."""

import httpx
import pytest
import yt_dlp

from app.services.sources import YouTubeProvider
from app.workers.lifecycle import ProcessingError

pytestmark = pytest.mark.anyio

REF = YouTubeProvider().parse("https://www.youtube.com/watch?v=ZA-tUyM_y7s")


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeYoutubeDL:
    """Stands in for yt_dlp.YoutubeDL; records whether a download was requested."""

    outcome = None
    downloads = []

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        FakeYoutubeDL.downloads.append(download)
        if isinstance(FakeYoutubeDL.outcome, Exception):
            raise FakeYoutubeDL.outcome
        return FakeYoutubeDL.outcome


@pytest.fixture
def ytdlp(monkeypatch):
    FakeYoutubeDL.downloads = []
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return FakeYoutubeDL


def oembed_returning(status: int):
    async def handler(request):
        return httpx.Response(status, json={"title": "from oembed", "author_name": "x"} if status == 200 else {})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_embedding_disabled_but_public_video_is_accepted_via_metadata_lookup(ytdlp):
    ytdlp.outcome = {"title": "CS229: Machine Learning, Lecture 1", "uploader": "Stanford Online"}

    info = await YouTubeProvider().check_access(REF, oembed_returning(401))

    assert (info.title, info.author) == ("CS229: Machine Learning, Lecture 1", "Stanford Online")
    assert ytdlp.downloads == [False]  # metadata only: nothing is downloaded during the pre-check


@pytest.mark.parametrize(
    "provider_message,code,expected",
    [
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "source_private", "private"),
        ("ERROR: [youtube] abc: Join this channel to get access to members-only content", "source_restricted", "members"),
        ("ERROR: [youtube] abc: Sign in to confirm your age", "source_restricted", "age-restricted"),
        ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "source_blocked", "verification"),
        ("ERROR: [youtube] abc: Video unavailable", "source_not_found", "no longer available"),
        ("ERROR: something unexpected", "source_restricted", "wouldn't let this video be accessed"),
    ],
)
async def test_restricted_video_reports_the_actual_reason(ytdlp, provider_message, code, expected):
    ytdlp.outcome = yt_dlp.utils.DownloadError(provider_message)

    with pytest.raises(ProcessingError) as caught:
        await YouTubeProvider().check_access(REF, oembed_returning(401))

    assert caught.value.code == code
    assert expected in caught.value.message
    assert caught.value.retryable is False
    assert ytdlp.downloads == [False]
    assert "provider_error" in caught.value.details


async def test_oembed_success_needs_no_fallback(ytdlp):
    info = await YouTubeProvider().check_access(REF, oembed_returning(200))
    assert info.title == "from oembed"
    assert ytdlp.downloads == []
