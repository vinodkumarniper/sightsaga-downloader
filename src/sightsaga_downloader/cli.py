"""Command-line interface and yt-dlp integration for SightSaga Downloader."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse


DEFAULT_FORMAT = (
    "bestvideo[height<=1080]+bestaudio/"
    "best[height<=1080]/bestvideo+bestaudio/best"
)


@dataclass(frozen=True)
class DownloadResult:
    url: str
    status: str
    title: str | None = None
    media_id: str | None = None
    extractor: str | None = None
    webpage_url: str | None = None
    error: str | None = None
    recorded_at: str = ""

    def with_timestamp(self) -> "DownloadResult":
        return DownloadResult(
            **{
                **asdict(self),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    if number > 1000:
        raise argparse.ArgumentTypeError("must not exceed 1000")
    return number


def validate_public_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Not a public HTTP(S) URL: {value!r}")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed")
    return value


def read_url_file(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Could not read URL file {path}: {exc}") from exc
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def collect_urls(positional: Iterable[str], url_file: Path | None) -> list[str]:
    candidates = list(positional)
    if url_file is not None:
        candidates.extend(read_url_file(url_file))

    urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        url = validate_public_url(candidate)
        if url not in seen:
            urls.append(url)
            seen.add(url)
    if not urls:
        raise ValueError("Provide at least one URL or use --url-file")
    return urls


def build_ydl_options(
    output_dir: Path,
    *,
    audio_only: bool,
    dry_run: bool,
    max_downloads: int,
    format_selector: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {
        "outtmpl": str(
            output_dir
            / "%(extractor_key)s"
            / "%(uploader|Unknown uploader)s"
            / "%(upload_date>%Y-%m-%d,Unknown date)s - %(title).180B [%(id)s].%(ext)s"
        ),
        "download_archive": str(output_dir / ".archive.txt"),
        "format": format_selector,
        "ignoreerrors": False,
        "lazy_playlist": True,
        "max_downloads": max_downloads,
        "merge_output_format": "mkv",
        "noplaylist": False,
        "overwrites": False,
        "continuedl": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "trim_file_name": 220,
        "restrictfilenames": False,
        "writedescription": True,
        "writeinfojson": True,
        "writethumbnail": True,
        "writesubtitles": True,
        "writeautomaticsub": False,
        "subtitleslangs": ["en", "en-orig", "-live_chat"],
        "subtitlesformat": "best",
        "quiet": False,
        "no_warnings": False,
        "simulate": dry_run,
        "skip_download": dry_run,
    }
    if audio_only:
        options.update(
            {
                "format": "bestaudio/best",
                "merge_output_format": None,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    },
                    {"key": "FFmpegMetadata"},
                    {"key": "EmbedThumbnail"},
                ],
            }
        )
    else:
        options["postprocessors"] = [{"key": "FFmpegMetadata"}]
    return options


def iter_entries(info: dict[str, Any] | None) -> Iterable[dict[str, Any]]:
    if not info:
        return
    entries = info.get("entries")
    if entries is not None:
        for entry in entries:
            if entry:
                yield from iter_entries(entry)
        return
    yield info


def result_from_info(requested_url: str, info: dict[str, Any], dry_run: bool) -> DownloadResult:
    return DownloadResult(
        url=requested_url,
        status="inspected" if dry_run else "downloaded",
        title=info.get("title"),
        media_id=str(info["id"]) if info.get("id") is not None else None,
        extractor=info.get("extractor_key") or info.get("extractor"),
        webpage_url=info.get("webpage_url") or info.get("original_url"),
    ).with_timestamp()


def append_manifest(path: Path, results: Iterable[DownloadResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for result in results:
            stream.write(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True) + "\n")


def download_urls(
    urls: Sequence[str],
    options: dict[str, Any],
    *,
    dry_run: bool,
    ydl_class: Any | None = None,
) -> list[DownloadResult]:
    from yt_dlp.utils import MaxDownloadsReached

    if ydl_class is None:
        from yt_dlp import YoutubeDL

        ydl_class = YoutubeDL

    results: list[DownloadResult] = []
    with ydl_class(options) as ydl:
        for url in urls:
            try:
                info = ydl.extract_info(url, download=not dry_run)
                entries = list(iter_entries(info))
                if entries:
                    results.extend(result_from_info(url, entry, dry_run) for entry in entries)
                else:
                    results.append(
                        DownloadResult(url=url, status="skipped", error="No media entries returned").with_timestamp()
                    )
            except MaxDownloadsReached:
                results.append(
                    DownloadResult(
                        url=url,
                        status="limit-reached",
                    ).with_timestamp()
                )
                break
            except Exception as exc:  # yt-dlp raises extractor-specific exception types
                results.append(
                    DownloadResult(
                        url=url,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                    ).with_timestamp()
                )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sightsaga-download",
        description="Archive publicly accessible media with metadata and duplicate protection.",
    )
    parser.add_argument("urls", metavar="URL", nargs="*", help="Public media or playlist URL")
    parser.add_argument("--url-file", type=Path, metavar="PATH", help="Text file with one URL per line")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("SIGHTSAGA_OUTPUT_DIR", "downloads")),
        metavar="DIR",
        help="Destination directory (default: downloads)",
    )
    parser.add_argument("--audio-only", action="store_true", help="Extract audio as MP3")
    parser.add_argument("--dry-run", action="store_true", help="Inspect metadata without downloading media")
    parser.add_argument(
        "--max-downloads",
        type=positive_int,
        default=positive_int(os.getenv("SIGHTSAGA_MAX_DOWNLOADS", "50")),
        metavar="N",
        help="Maximum playlist entries across the run (default: 50)",
    )
    parser.add_argument(
        "--format",
        dest="format_selector",
        default=os.getenv("SIGHTSAGA_FORMAT", DEFAULT_FORMAT),
        metavar="FORMAT",
        help="Advanced yt-dlp format selector",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        urls = collect_urls(args.urls, args.url_file)
    except ValueError as exc:
        parser.error(str(exc))

    options = build_ydl_options(
        args.output_dir,
        audio_only=args.audio_only,
        dry_run=args.dry_run,
        max_downloads=args.max_downloads,
        format_selector=args.format_selector,
    )
    print(f"SightSaga: processing {len(urls)} public URL(s)", file=sys.stderr)
    results = download_urls(urls, options, dry_run=args.dry_run)
    append_manifest(args.output_dir / "manifest.jsonl", results)

    for result in results:
        label = result.title or result.url
        print(f"[{result.status}] {label}")
        if result.error:
            print(f"  {result.error}", file=sys.stderr)

    failures = sum(result.status == "failed" for result in results)
    if failures:
        print(f"SightSaga: {failures} item(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
