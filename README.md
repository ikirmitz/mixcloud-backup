# mixcloud-backup

A toolkit for backing up your Mixcloud account — downloads uploads with optimal quality, and adds tracklist navigation to audio files via embedded lyrics tags or `.lrc` files.

## Table of Contents

- [mixcloud-backup](#mixcloud-backup)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
  - [Tools](#tools)
    - [1. Downloader](#1-downloader)
    - [2. Orphan Track Finder](#2-orphan-track-finder)
    - [3. Tracklist Generator](#3-tracklist-generator)
    - [4. LRC Embedder](#4-lrc-embedder)
  - [How Tracklists Work](#how-tracklists-work)
  - [Troubleshooting](#troubleshooting)
    - ["Skipping (no Mixcloud URL in tags)"](#skipping-no-mixcloud-url-in-tags)
    - ["Skipping (bad Mixcloud URL format)"](#skipping-bad-mixcloud-url-format)
    - ["Skipping (only X section(s))"](#skipping-only-x-sections)
    - ["Skipping (no timing information)"](#skipping-no-timing-information)
  - [Limitations](#limitations)
  - [Developer Setup](#developer-setup)
  - [Technical Details](#technical-details)
  - [Legal \& License](#legal--license)
    - [Legal Disclaimer](#legal-disclaimer)
    - [License](#license)

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repository-url>
cd mixcloud-backup
uv sync
```

## Quick Start

Download all uploads from a Mixcloud account:

```bash
uv run python src/mixcloud_downloader.py USERNAME
```

Download by playlist instead:

```bash
uv run python src/mixcloud_downloader.py USERNAME --playlists
```

## Tools

### 1. Downloader

Download all uploads from a Mixcloud account (default). Use `--playlists` to organize by playlist instead. Source codec is detected per-track only when transcoding to MP3.
Uploads that show on a host profile are resolved using the canonical Mixcloud URL, so host-attributed shows download correctly.

```bash
uv run python src/mixcloud_downloader.py USERNAME

# Download by playlist instead of uploads
uv run python src/mixcloud_downloader.py USERNAME --playlists

# Download latest 25 uploads
uv run python src/mixcloud_downloader.py USERNAME --limit 25

# Download uploads since a date
uv run python src/mixcloud_downloader.py USERNAME --since 2024-01-01

# Apply limits in playlist mode too
uv run python src/mixcloud_downloader.py USERNAME --playlists --limit 50 --since 2024-01-01
```

Tracklists from the Mixcloud API are embedded as lyrics when the file format supports it: MP3 (USLT), M4A/MP4 (©lyr), and Ogg/Opus (Vorbis comments). For unsupported formats, a `.lrc` file is written instead.

| Option | Description |
|--------|-------------|
| `--output, -o` | Output directory (default: current directory) |
| `--archive, -a` | Archive file to skip already-downloaded tracks (default: `~/mixcloud-archive.txt`) |
| `--playlists` | Download by playlist (default: all uploads) |
| `--to-mp3` | Transcode audio to MP3 (default: keep original container) |
| `--dry-run` | List uploads or playlists without downloading |
| `--no-embed` | Skip tracklist embedding |
| `--write-lrc` | Also write separate `.lrc` files alongside MP3s |
| `--limit` | Limit number of tracks to download |
| `--since` | Only download uploads on/after `YYYY-MM-DD` |

**MP3 quality selection (only with --to-mp3):**

| Source Format | MP3 Quality | Typical Bitrate |
|--------------|-------------|-----------------|
| webm/opus (newer uploads) | `-q:a 0` | ~245 kbps VBR |
| m4a/aac (older uploads) | `-q:a 2` | ~170 kbps VBR |

**Output structure:**
```
./
├── Uploader/
│   └── Uploads/ or Playlist Name/
│       ├── 20240101 - Mix Title.opus  (default: original container)
│       ├── 20240101 - Mix Title.m4a   (older uploads)
│       ├── 20240101 - Mix Title.mp3   (with --to-mp3)
│       └── 20240101 - Mix Title.lrc   (when embedding isn't possible or with --write-lrc)
└── metadata/
    └── Uploader/
        └── Playlist Name/
            └── 20240101 - Mix Title.info.json
```

### 2. Orphan Track Finder

Find uploads that aren't in any playlist. Optionally download them.

```bash
# List orphan tracks
uv run python src/mixcloud_orphans.py USERNAME

# Download orphan tracks
uv run python src/mixcloud_orphans.py USERNAME --download
```

| Option | Description |
|--------|-------------|
| `--download` | Download orphan tracks (default: just list them) |
| `--output, -o` | Output directory |
| `--archive, -a` | Archive file |
| `--to-mp3` | Transcode audio to MP3 (default: keep original container) |
| `--no-embed` | Skip tracklist embedding |
| `--write-lrc` | Write separate `.lrc` files |

### 3. Tracklist Generator

For audio files you already have — fetches tracklists from the Mixcloud API and embeds them as lyrics. Supports `.mp3`, `.m4a`, `.mp4`, `.opus`, `.ogg`, and `.oga`.

```bash
uv run python src/mixcloud_match_to_lrc.py /path/to/your/music
```

This is useful for existing collections that weren't downloaded with the downloader above.

**Requires**: Each file must have a Mixcloud URL in its metadata tags (`TXXX:purl`, `purl`, `url`, `WXXX:purl`, `WPUB`, `WOAS`, or `comment`). Files downloaded with yt-dlp from Mixcloud already have this.

| Option | Description |
|--------|-------------|
| `--no-embed` | Skip embedding lyrics in audio tags |
| `--write-lrc` | Write separate `.lrc` files (default: embed only) |

### 4. LRC Embedder

Embed existing `.lrc` files into their matching audio files (same filename, different extension). Original `.lrc` files are preserved.

```bash
uv run python src/embed_lrc.py /path/to/your/music
```

No Mixcloud API access needed — this is a purely local operation.

## How Tracklists Work

Tracklists are stored in [LRC format](https://en.wikipedia.org/wiki/LRC_(file_format)) — timestamped text that media players can display for chapter/track navigation:

```
[ar:username]
[ti:Mix Title]

[00:00.00] 01. Artist One – Song One
[05:30.50] 02. Artist Two – Song Two
[12:45.20] 03. Artist Three – Song Three
```

This content is embedded directly in the audio file when supported (MP3 USLT, M4A/MP4 ©lyr, Ogg/Opus Vorbis comments). For unsupported formats, the downloader writes a `.lrc` file instead. Optionally, `.lrc` files can always be written with `--write-lrc`.

When the Mixcloud API doesn't provide timestamps, they're calculated as evenly-spaced intervals based on the file duration. Files with fewer than 2 sections are skipped.

## Troubleshooting

### "Skipping (no Mixcloud URL in tags)"

The tracklist generator needs a Mixcloud URL in the MP3's metadata to look up the tracklist. Files downloaded via yt-dlp from Mixcloud have this automatically. For other files, add the URL to the `TXXX:purl`, `WPUB`, `WOAS`, or `comment` tag using a tool like [Mp3tag](https://www.mp3tag.de/).

### "Skipping (bad Mixcloud URL format)"

URL must match: `https://www.mixcloud.com/username/slug/`

### "Skipping (only X section(s))"

Need at least 2 tracks/chapters for useful navigation.

### "Skipping (no timing information)"

The API didn't provide timestamps and the audio duration couldn't be read.

## Limitations

- Overwrites existing `.lrc` files without warning
- Processes files sequentially (not in parallel)
- No retry logic for network failures
- WebM containers do not support embedded lyrics tags here; `.lrc` is used instead

## Developer Setup

To install developer and test dependencies (such as pytest), use the `dev` extra group:

```bash
uv sync --extra dev
```

To run the test suite:

```bash
uv run pytest
```

## Technical Details

For developers and LLMs: See [agents.md](agents.md) for detailed technical documentation including API schemas, function signatures, validation rules, and modification points.

## Legal & License

### Legal Disclaimer

**For Personal Use Only**: This tool is intended for backing up your own Mixcloud content or content you have permission to download. Users are solely responsible for ensuring their use complies with:

- Mixcloud's Terms of Service
- Copyright laws in their jurisdiction
- Rights of content creators and copyright holders

**No Warranty**: This software is provided "as is" without warranty of any kind. Downloaded content may be subject to copyright protection. The authors and contributors are not responsible for any misuse of this tool.

**Respect Content Creators**: Please support artists and DJs by streaming their content on Mixcloud when possible. This tool is meant for personal archival purposes, not for redistribution or commercial use.

### License

This project is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0) - see the [LICENSE](LICENSE) file for details.

**Commercial use is prohibited.**
