import json
import tempfile
import unittest
from pathlib import Path

from yt_dlp.utils import MaxDownloadsReached

from sightsaga_downloader.cli import (
    DEFAULT_FORMAT,
    DownloadResult,
    append_manifest,
    build_ydl_options,
    collect_urls,
    download_urls,
    positive_int,
    validate_public_url,
)


class UrlTests(unittest.TestCase):
    def test_accepts_http_and_https(self):
        self.assertEqual(validate_public_url("https://example.com/a"), "https://example.com/a")
        self.assertEqual(validate_public_url(" http://example.com/b "), "http://example.com/b")

    def test_rejects_non_http_and_credentials(self):
        for value in ("file:///tmp/a", "javascript:alert(1)", "example.com/a"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_public_url(value)
        with self.assertRaises(ValueError):
            validate_public_url("https://user:pass@example.com/a")

    def test_collects_deduplicated_urls_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sources.txt"
            source.write_text("# note\nhttps://example.com/b\n\nhttps://example.com/a\n", encoding="utf-8")
            self.assertEqual(
                collect_urls(["https://example.com/a"], source),
                ["https://example.com/a", "https://example.com/b"],
            )

    def test_requires_a_url(self):
        with self.assertRaises(ValueError):
            collect_urls([], None)

    def test_positive_int_bounds(self):
        self.assertEqual(positive_int("1"), 1)
        self.assertEqual(positive_int("1000"), 1000)
        for value in ("0", "1001", "x"):
            with self.subTest(value=value), self.assertRaises(Exception):
                positive_int(value)


class OptionsTests(unittest.TestCase):
    def test_video_options(self):
        with tempfile.TemporaryDirectory() as directory:
            options = build_ydl_options(
                Path(directory),
                audio_only=False,
                dry_run=False,
                max_downloads=8,
                format_selector=DEFAULT_FORMAT,
            )
            self.assertEqual(options["format"], DEFAULT_FORMAT)
            self.assertEqual(options["max_downloads"], 8)
            self.assertFalse(options["simulate"])
            self.assertTrue(options["writeinfojson"])

    def test_audio_options(self):
        with tempfile.TemporaryDirectory() as directory:
            options = build_ydl_options(
                Path(directory),
                audio_only=True,
                dry_run=True,
                max_downloads=1,
                format_selector="ignored",
            )
            self.assertEqual(options["format"], "bestaudio/best")
            self.assertTrue(options["simulate"])
            self.assertEqual(options["postprocessors"][0]["key"], "FFmpegExtractAudio")


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def extract_info(self, url, download):
        if "limit" in url:
            raise MaxDownloadsReached()
        if "fail" in url:
            raise RuntimeError("fixture failure")
        return {
            "_type": "playlist",
            "entries": [
                {
                    "id": "abc123",
                    "title": "Public sample",
                    "extractor_key": "Fixture",
                    "webpage_url": url,
                }
            ],
        }


class DownloadTests(unittest.TestCase):
    def test_max_downloads_is_a_clean_stop(self):
        urls = [
            "https://example.com/ok",
            "https://example.com/limit",
            "https://example.com/not-reached",
        ]
        results = download_urls(urls, {}, dry_run=False, ydl_class=FakeYoutubeDL)
        self.assertEqual(
            [result.status for result in results],
            ["downloaded", "limit-reached"],
        )

    def test_download_results_and_failures(self):
        urls = ["https://example.com/ok", "https://example.com/fail"]
        results = download_urls(urls, {}, dry_run=False, ydl_class=FakeYoutubeDL)
        self.assertEqual([result.status for result in results], ["downloaded", "failed"])
        self.assertEqual(results[0].media_id, "abc123")
        self.assertIn("fixture failure", results[1].error)

    def test_appends_jsonl_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.jsonl"
            result = DownloadResult(url="https://example.com/a", status="downloaded").with_timestamp()
            append_manifest(manifest, [result])
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "downloaded")
            self.assertTrue(data["recorded_at"])


if __name__ == "__main__":
    unittest.main()
