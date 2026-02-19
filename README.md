# mixcloud-lrc

A toolkit for backing up your Mixcloud account — downloads playlists with optimal quality, and adds tracklist navigation to MP3 files via embedded lyrics tags.

## Tools

### 1. Playlist Downloader

Download all playlists from a Mixcloud account. Source codec is detected per-track to choose the right MP3 quality (avoiding bloated files from low-quality sources).

```bash
uv run python src/mixcloud_downloader.py USERNAME
```

Tracklists from the Mixcloud API are automatically embedded as lyrics (USLT tag) in each downloaded MP3, so media players can display track/chapter navigation. No extra steps needed.

| Option | Description |
|--------|-------------|
| `--output, -o` | Output directory (default: current directory) |
| `--archive, -a` | Archive file to skip already-downloaded tracks (default: `~/mixcloud-archive.txt`) |
| `--dry-run` | List playlists without downloading |
| `--no-embed` | Skip tracklist embedding |
| `--write-lrc` | Also write separate `.lrc` files alongside MP3s |

**Quality selection:**

| Source Format | MP3 Quality | Typical Bitrate |
|--------------|-------------|-----------------|
| webm/opus (newer uploads) | `-q:a 0` | ~245 kbps VBR |
| m4a/aac (older uploads) | `-q:a 2` | ~170 kbps VBR |

**Output structure:**
```
./
├── Uploader/
│   └── Playlist Name/
│       ├── 20240101 - Mix Title.mp3  (with embedded tracklist)
│       └── 20240101 - Mix Title.lrc  (only with --write-lrc)
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
| `--no-embed` | Skip tracklist embedding |
| `--write-lrc` | Write separate `.lrc` files |

### 3. Tracklist Generator

For MP3 files you already have — fetches tracklists from the Mixcloud API and embeds them as lyrics.

```bash
uv run python src/mixcloud_match_to_lrc.py /path/to/your/music
```

This is useful for existing collections that weren't downloaded with the downloader above.

**Requires**: Each MP3 must have a Mixcloud URL in its metadata tags (`TXXX:purl`, `purl`, `WXXX:purl`, `WPUB`, `WOAS`, or `comment`). Files downloaded with yt-dlp from Mixcloud already have this.

| Option | Description |
|--------|-------------|
| `--no-embed` | Skip embedding lyrics in MP3 USLT tag |
| `--write-lrc` | Write separate `.lrc` files (default: embed only) |

### 4. LRC Embedder

Embed existing `.lrc` files into their matching `.mp3` files (same filename, different extension). Original `.lrc` files are preserved.

```bash
uv run python src/embed_lrc.py /path/to/your/music
```

No Mixcloud API access needed — this is a purely local operation.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repository-url>
cd mixcloud-lrc
uv sync
```

## How the Tracklist Works

Tracklists are stored in [LRC format](https://en.wikipedia.org/wiki/LRC_(file_format)) — timestamped text that media players can display for chapter/track navigation:

```
[ar:username]
[ti:Mix Title]

[00:00.00] 01. Artist One – Song One
[05:30.50] 02. Artist Two – Song Two
[12:45.20] 03. Artist Three – Song Three
```

This content is embedded directly in the MP3's USLT (lyrics) tag, making it portable with the file. Optionally, it can also be written as a separate `.lrc` file.

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

## Technical Details

For developers and LLMs: See [agents.md](agents.md) for detailed technical documentation including API schemas, function signatures, validation rules, and modification points.
