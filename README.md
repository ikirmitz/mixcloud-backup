# mixcloud-lrc

Backup your Mixcloud account and generate LRC chapter files for media player navigation.

## What is this?

This project provides tools for working with Mixcloud content:

1. **Automated Downloader** - Download all playlists from a Mixcloud account with intelligent quality selection
2. **LRC Generator** - Fetch tracklists from Mixcloud API and embed them as lyrics (USLT tag) in MP3 files
3. **LRC Embedder** - Embed existing `.lrc` files into MP3 files
4. **Orphan Finder** - Find and download tracks that aren't in any playlist

The downloader automatically detects whether each track uses the newer high-quality format (opus) or older format (aac), and adjusts MP3 encoding quality accordingly to avoid bloating files from low-quality sources.

By default, tracklist data is embedded directly into MP3 files as USLT (lyrics) tags, making the chapter/track information portable with the file.

## Quick Start

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer
- MP3 files with Mixcloud URLs in their metadata

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd mixcloud-lrc

# Install dependencies using uv
uv sync
```

### Usage

Process all MP3 files in a directory:

```bash
uv run python src/mixcloud_match_to_lrc.py /path/to/your/podcasts
```

Or process the current directory:

```bash
uv run python src/mixcloud_match_to_lrc.py
```

## Automated Downloads

Download all playlists from a Mixcloud account:

```bash
uv run python src/mixcloud_downloader.py USERNAME
```

### Options

```bash
# Specify output directory
uv run python src/mixcloud_downloader.py USERNAME --output ~/Music/mixcloud

# Use custom archive file (tracks what's already downloaded)
uv run python src/mixcloud_downloader.py USERNAME --archive ~/my-archive.txt

# Preview playlists without downloading
uv run python src/mixcloud_downloader.py USERNAME --dry-run

# Skip lyrics embedding (download only)
uv run python src/mixcloud_downloader.py USERNAME --no-embed

# Write separate .lrc files (in addition to embedding)
uv run python src/mixcloud_downloader.py USERNAME --write-lrc
```

### Quality Selection

The downloader automatically detects the source audio format and applies appropriate MP3 quality:

| Source Format | Used By | MP3 Quality | Result |
|--------------|---------|-------------|--------|
| webm/opus | Newer uploads (HQ) | `-q:a 0` | ~245 kbps VBR |
| m4a/aac | Older uploads | `-q:a 2` | ~170 kbps VBR |

This prevents unnecessarily large files when the source audio is already low quality.

### Output Structure

```
./
├── Uploader/
│   └── Playlist Name/
│       ├── 20240101 - Mix Title.mp3  (with embedded lyrics)
│       ├── 20240101 - Mix Title.lrc  (only if --write-lrc used)
│       └── ...
└── metadata/
    └── Uploader/
        └── Playlist Name/
            └── 20240101 - Mix Title.info.json
```

## Embed Existing LRC Files

If you have existing `.lrc` files that you want to embed into their matching MP3 files:

```bash
uv run python src/embed_lrc.py /path/to/your/music
```

This finds all `.lrc` files and embeds their content into the matching `.mp3` file (same filename, different extension). The original `.lrc` files are preserved.

## Find Orphan Tracks

Find tracks that aren't in any playlist:

```bash
# List orphan tracks
uv run python src/mixcloud_orphans.py USERNAME

# Download orphan tracks
uv run python src/mixcloud_orphans.py USERNAME --download
```

## How It Works

1. Scans your MP3 files for embedded Mixcloud URLs (in ID3 tags)
2. Fetches the tracklist from Mixcloud's API
3. Embeds the tracklist as USLT (lyrics) tag in the MP3 file
4. Optionally writes `.lrc` files with timestamped chapters/tracks
5. If timing data is missing, automatically calculates evenly-spaced timestamps based on file duration
6. Only processes files with 2 or more sections

## Requirements

Your MP3 files must have a Mixcloud URL embedded in one of these ID3 tags:
- `TXXX:purl` (User-defined text frame) - most common
- `purl` (Simple metadata tag for MP4/M4A files)
- `WPUB` (Podcast URL)
- `WOAS` (Official Audio Source URL)
- `WXXX:purl` (User-defined URL frame)
- `comment` (Comment field containing a Mixcloud URL)

## Output Example

For a podcast at `example.mp3`, the tool creates `example.lrc`:

```
[ar:username]
[ti:example]

[00:00.00] Introduction
[05:30.50] DJ Snake – Taki Taki
[12:45.20] Interview with Guest
```

## What Gets Skipped

The tool will skip files that:
- Don't have a Mixcloud URL in their metadata
- Have an invalid or malformed Mixcloud URL
- Have fewer than 2 sections (tracks or chapters)
- Have no timing information and no readable audio duration

You'll see a message explaining why each file was skipped.

## Smart Timestamp Calculation

When Mixcloud doesn't provide timestamp data for tracks:
- The tool automatically calculates evenly-spaced timestamps
- Based on the audio file duration
- Example: 60-minute file with 6 tracks → tracks at 0:00, 10:00, 20:00, 30:00, 40:00, 50:00

## Troubleshooting

### No LRC files are created

Check that your MP3 files have Mixcloud URLs embedded. You can use a tool like [Mp3tag](https://www.mp3tag.de/) to view and edit ID3 tags.

### "Skipping (no podcast URL)" message

The MP3 file doesn't have a Mixcloud URL in its metadata. Add the URL to the TXXX:purl, WPUB, WOAS, or comment tag.

### "Bad Mixcloud URL" message

The URL format isn't recognized. Should be: `https://www.mixcloud.com/username/slug/`

### "Skipping (only X section(s))" message

The file has fewer than 2 tracks/chapters. Need at least 2 to create a useful LRC file.

### "Skipping (no timing information)" message

The API didn't provide timestamps and the audio file duration couldn't be read.

## Features

### Downloader
- Automatically discovers all playlists for a Mixcloud account
- Intelligent quality selection based on source format (opus vs aac)
- Download archive to resume interrupted sessions
- Embedded metadata, thumbnails, and info.json files
- Rate limiting with configurable sleep intervals
- Automatic lyrics embedding for downloaded files

### LRC Generator
- Embeds tracklists as USLT (lyrics) tag in MP3 files
- Optionally writes separate .lrc files
- Supports both DJ mixes (with track listings) and podcasts (with chapters)
- Automatic timestamp calculation when API data is missing
- Recursive directory scanning
- Batch processing with error handling
- UTF-8 encoding support
- Multiple ID3 tag format support
- No API key required

### LRC Embedder
- Embeds existing .lrc files into matching MP3 files
- Preserves original .lrc files
- Recursive directory scanning

### Orphan Finder
- Discovers tracks not in any playlist
- Optional download with same quality settings as main downloader

## Limitations

- Overwrites existing LRC files without warning
- Requires exact Mixcloud URL format
- Processes files sequentially (not in parallel)
- No retry logic for network failures

## Technical Details

For developers and LLMs: See [agents.md](agents.md) for detailed technical documentation including API schemas, function signatures, validation rules, and modification points.

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
