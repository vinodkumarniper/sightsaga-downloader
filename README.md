# SightSaga Downloader

SightSaga Downloader is a small, automation-friendly command-line tool for archiving **publicly accessible** video and audio. It wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp) with safe defaults, duplicate protection, metadata manifests, and a manual GitHub Actions workflow.

> Only download media you own or have permission to archive. This project does not accept cookies or credentials and does not circumvent DRM, paywalls, or access controls.

## Features

- Accepts one or more public `http://` or `https://` URLs
- Downloads best-quality video (up to 1080p by default) or audio-only files
- Writes thumbnails, descriptions, subtitles, and yt-dlp metadata sidecars
- Uses a persistent archive file so reruns skip completed downloads
- Appends a machine-readable JSON Lines manifest for every success, skip, and failure
- Supports playlists with a configurable per-run download limit
- Includes a dry-run mode for inspecting URLs without downloading media
- Runs locally or from the repository's **Download public media** GitHub Action

## Local installation

Python 3.10+ and `ffmpeg` are required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
```

Download one URL:

```bash
sightsaga-download "https://example.com/public-video"
```

Download several URLs, including playlists:

```bash
sightsaga-download --url-file sources.txt --max-downloads 25
```

Audio only:

```bash
sightsaga-download --audio-only "https://example.com/public-audio"
```

Inspect metadata without downloading:

```bash
sightsaga-download --dry-run "https://example.com/public-video"
```

By default, media is stored in `downloads/`, completed IDs are recorded in `downloads/.archive.txt`, and results are appended to `downloads/manifest.jsonl`.

## GitHub Actions

1. Open the repository's **Actions** tab.
2. Select **Download public media**.
3. Choose **Run workflow**.
4. Paste one public URL per line, choose the mode and limit, then run it.
5. When the job completes, download the `sightsaga-downloads-*` artifact.

Artifacts expire after 7 days. GitHub-hosted runners have storage, bandwidth, and execution limits, so use the workflow for modest public-footage jobs rather than large archives.

## Command reference

```text
usage: sightsaga-download [-h] [--url-file PATH] [--output-dir DIR]
                          [--audio-only] [--dry-run]
                          [--max-downloads N] [--format FORMAT]
                          [URL ...]
```

- `URL`: one or more public media or playlist URLs
- `--url-file`: text file containing one URL per line; blank lines and `#` comments are ignored
- `--output-dir`: download directory (default: `downloads`)
- `--audio-only`: extract audio as MP3
- `--dry-run`: resolve metadata without downloading media
- `--max-downloads`: stop after this many playlist entries across the run (default: `50`)
- `--format`: advanced yt-dlp format selector; ignored in audio-only mode

Environment variables:

- `SIGHTSAGA_OUTPUT_DIR`
- `SIGHTSAGA_MAX_DOWNLOADS`
- `SIGHTSAGA_FORMAT`

## Development

The test suite uses only the Python standard library:

```bash
python -m unittest discover -s tests -v
```

## License

MIT
