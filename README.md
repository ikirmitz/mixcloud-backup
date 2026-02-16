# mixcloud-lrc

Convert Mixcloud podcast tracklists to LRC files for chapter navigation in your media player.

## What is this?

This tool reads your Mixcloud podcast MP3 files and generates `.lrc` files (the same format used for song lyrics) containing timestamped chapter markers. This enables chapter navigation in media players that support LRC files.

## Quick Start

### Prerequisites

- Python 3.12 or higher
- MP3 files with Mixcloud URLs in their metadata

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd mixcloud-lrc

# Install dependencies
pip install mutagen requests
```

### Usage

Process all MP3 files in a directory:

```bash
python src/mixcloud_match_to_lrc.py /path/to/your/podcasts
```

Or process the current directory:

```bash
python src/mixcloud_match_to_lrc.py
```

## How It Works

1. Scans your MP3 files for embedded Mixcloud URLs (in ID3 tags)
2. Fetches the tracklist from Mixcloud's API
3. Generates `.lrc` files with timestamped chapters/tracks
4. If timing data is missing, automatically calculates evenly-spaced timestamps based on file duration
5. Only creates LRC files for files with 2 or more sections

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

- Supports both DJ mixes (with track listings) and podcasts (with chapters)
- Automatic timestamp calculation when API data is missing
- Recursive directory scanning
- Batch processing with error handling
- UTF-8 encoding support
- Multiple ID3 tag format support
- No API key required

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
