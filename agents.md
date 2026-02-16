# mixcloud-lrc Technical Reference

## Overview

`mixcloud-lrc` is a Python utility that converts Mixcloud tracklists (for DJ mixes and podcasts) into LRC (lyric) files. It extracts Mixcloud URLs from MP3 metadata, queries the Mixcloud GraphQL API for track/chapter information, and generates synchronized LRC files with timestamps.

**Purpose**: Enable chapter/track navigation in media players by converting Mixcloud tracklist data to the LRC format.

## Project Structure

```
mixcloud-lrc/
├── src/
│   └── mixcloud_match_to_lrc.py    # Main implementation
├── main.py                          # Entry point placeholder
├── pyproject.toml                   # Project configuration
├── README.md                        # User documentation
└── agents.md                        # This file
```

## Core Components

### Main Module: `src/mixcloud_match_to_lrc.py`

**Dependencies**:
- `mutagen.File` - Universal audio metadata reading (supports MP3, MP4/M4A, etc.)
- `requests` - HTTP client for GraphQL API
- `pathlib.Path` - File system operations
- `re` - URL pattern matching
- `json` - JSON handling

**Constants**:
- `GRAPHQL_URL = "https://app.mixcloud.com/graphql"`

### Key Functions

#### `extract_lookup(url: str) -> tuple[str | None, str | None]`
**Purpose**: Parse Mixcloud URL to extract username and slug
**Pattern**: `r"mixcloud\.com/([^/]+)/([^/]+)/?"`
**Returns**: `(username, slug)` tuple or `(None, None)` if invalid
**Example**: `"https://www.mixcloud.com/user/mix-name/"` → `("user", "mix-name")`

#### `fmt(sec: float) -> str`
**Purpose**: Convert seconds to LRC timestamp format
**Format**: `[MM:SS.CC]` where MM=minutes, SS=seconds, CC=centiseconds
**Example**: `fmt(65.5)` → `"[01:05.50]"`

#### `process_mp3(mp3_path: Path) -> None`
**Purpose**: Main processing logic for a single MP3 file

**Processing Steps**:
1. Read audio file and extract duration
2. Read metadata tags
3. Extract Mixcloud URL from tags (TXXX:purl, purl, WPUB, WOAS, WXXX:purl, comment)
4. Parse username and slug from URL
5. Query GraphQL API
6. Validate section count (minimum 2)
7. Check for timing data; if missing, calculate evenly-spaced timestamps
8. Generate LRC file

**Exit Conditions**:
- No tags → skip
- No podcast URL → skip with message
- Bad URL format → skip with message
- Less than 2 sections → skip with message
- No timing data and no audio duration → skip with message

#### `walk(root: str) -> None`
**Purpose**: Recursively process all MP3 files in directory
**Error Handling**: Catches exceptions for individual files, continues processing

## GraphQL API Integration

### Endpoint
- URL: `https://app.mixcloud.com/graphql`
- Method: POST
- Authentication: None required

### Query Structure
```graphql
query Tracklist($lookup: CloudcastLookup!) {
  cloudcastLookup(lookup: $lookup) {
    sections {
      __typename
      ... on SectionBase { startSeconds }
      ... on TrackSection { artistName songName }
      ... on ChapterSection { chapter }
    }
  }
}
```

### Variables
```json
{
  "lookup": {
    "username": "string",
    "slug": "string"
  }
}
```

### Response Schema
```json
{
  "data": {
    "cloudcastLookup": {
      "sections": [
        {
          "__typename": "TrackSection" | "ChapterSection",
          "startSeconds": float | null,
          "artistName": "string",      // TrackSection only
          "songName": "string",         // TrackSection only
          "chapter": "string"           // ChapterSection only
        }
      ]
    }
  }
}
```

**Note**: `startSeconds` can be `null` for some uploads. The tool handles this by calculating evenly-spaced timestamps.

## Data Flow

1. **Input**: MP3 file with metadata containing Mixcloud URL
2. **Audio Duration**: Extract file duration using mutagen
3. **Tag Extraction**: Check TXXX:purl, purl, WPUB, WOAS, WXXX:purl, comment tags
4. **URL Parsing**: Extract username and slug using regex
5. **API Request**: POST to GraphQL endpoint with CloudcastLookup variables
6. **Response Processing**: Parse sections array from JSON response
7. **Timestamp Handling**:
   - If API provides timestamps → use them
   - If all null → calculate evenly-spaced based on file duration
8. **LRC Generation**: Write formatted file with metadata header and timestamped entries
9. **Output**: `.lrc` file in same directory as source MP3

## Validation Rules

### Section Count Validation
- Minimum 2 sections required (tracks or chapters)
- Counts total sections, not just chapters
- Rationale: Need at least 2 points for meaningful navigation

### Timestamp Validation
- Count sections with valid (non-null) timestamps
- If less than 2 have timestamps AND audio duration is available:
  - Calculate `interval = duration / section_count`
  - Assign `section[i].startSeconds = i * interval`
- If no duration available: skip file

### URL Validation
- Must match pattern: `mixcloud.com/[username]/[slug]/`
- Both username and slug required
- Protocol (http/https) and trailing slashes are flexible

### Tag Priority Order
1. `TXXX:purl` (ID3v2 user-defined text frame) - most common
2. `purl` (simple metadata tag for MP4/M4A)
3. `WXXX:purl` (ID3v2 user-defined URL frame)
4. `WPUB` (Official podcast/user web page)
5. `WOAS` (Official audio source web page)
6. `comment` (Comment field containing Mixcloud URL)

## LRC Output Format

### File Structure
```
[ar:{username}]           # Artist metadata from Mixcloud username
[ti:{filename}]           # Title metadata from MP3 filename (no extension)
                          # Blank line
[00:00.00] {content}      # Timestamped entries
[05:30.50] {content}
...
```

### Content Generation Logic
```python
for s in sections:
    if s["__typename"] == "TrackSection":
        title = f'{s["artistName"]} – {s["songName"]}'  # En-dash (U+2013)
    else:
        title = s.get("chapter", "")  # ChapterSection or other
    f.write(f"{fmt(s['startSeconds'])} {title}\n")
```

**Formatting**:
- TrackSection → "Artist – Song" (with en-dash)
- ChapterSection → chapter text directly
- Other sections → empty string if chapter field missing

## Error Handling

### File-Level Error Handling
All exceptions during individual file processing are caught and logged:
```python
try:
    process_mp3(path)
except Exception as e:
    print(f"Error on {path}: {e}")
```

**Behavior**:
- Logs error to console
- Continues to next file
- Doesn't stop batch processing

### Expected Error Scenarios
1. **Network failures**: `requests.post()` timeouts or connection errors
2. **JSON parsing**: Malformed API responses
3. **File I/O**: Permission errors, disk full
4. **Metadata reading**: Corrupted files, unsupported formats
5. **Missing keys**: KeyError if API response structure changes

### Skip Conditions (Not Errors)
Files are skipped with informative messages for:
- No metadata tags
- No podcast URL in tags
- Invalid URL format
- Fewer than 2 sections
- No timing data and no audio duration

## File System Behavior

### Input Processing
- **Pattern**: `*.mp3` (case-sensitive)
- **Mode**: Recursive traversal using `Path.rglob()`
- **Starting point**: Command-line argument or current directory
- **Order**: Filesystem order (non-deterministic)

### Output Generation
- **Location**: Same directory as source MP3
- **Naming**: `{basename}.lrc` (replaces .mp3 extension)
- **Overwrite**: Yes, without warning
- **Encoding**: UTF-8

## Command-Line Interface

### Usage
```bash
uv run python src/mixcloud_match_to_lrc.py [directory]
```

**Arguments**:
- `directory`: Optional path to process (default: current directory)

**Examples**:
```bash
uv run python src/mixcloud_match_to_lrc.py                    # Process current directory
uv run python src/mixcloud_match_to_lrc.py /path/to/podcasts  # Process specific directory
```

## Dependencies

### Package Management
This project uses **uv** for dependency management. Install dependencies with:
```bash
uv sync
```

### Required Packages
- **mutagen** ≥ 1.47.0: Multimedia tagging library (reads MP3, MP4, FLAC, etc.)
- **requests** ≥ 2.32.5: HTTP library for API calls

### Standard Library
- `pathlib`: Modern file path operations
- `re`: Regular expression matching
- `json`: JSON encoding/decoding
- `sys`: Command-line arguments

## Key Design Decisions

### Why Mutagen's Generic File Reader?
- Handles multiple formats (MP3, MP4/M4A) automatically
- Different tag formats (ID3v2, MP4 atoms) use different field names
- Universal API simplifies tag reading

### Why Calculate Timestamps?
- Many Mixcloud uploads lack embedded timing data
- Users still want LRC files for navigation
- Evenly-spaced timestamps better than nothing
- Based on actual file duration for accuracy

### Why En-dash (–) Instead of Hyphen (-)?
- Typographically correct for "Artist – Song" format
- Matches Mixcloud's own formatting
- Better visual separation

### Why Skip Files with < 2 Sections?
- LRC files need at least 2 timestamps to be useful
- Single-section files don't benefit from chapter navigation
- Avoids creating useless files

## Modification Guide

### Change Timestamp Calculation Method
Modify the interval calculation to use different spacing:
```python
# Linear spacing (current)
interval = audio_duration / len(sections)

# Logarithmic spacing (tracks get longer)
import math
interval = audio_duration / (sum(math.log(i+2) for i in range(len(sections))))
```

### Add Additional ID3 Tags
Add to the tag checking chain:
```python
elif "YOUR_TAG_HERE" in tags:
    url = str(tags["YOUR_TAG_HERE"])
```

### Change Minimum Section Requirement
Modify the threshold:
```python
if section_count < 3:  # Changed from 2 to 3
    print(f"Skipping (only {section_count} section(s)): {mp3_path}")
    return
```

### Output to Different Directory
Change the output path calculation:
```python
output_dir = Path("/custom/output/path")
lrc_path = output_dir / mp3_path.with_suffix(".lrc").name
```

## Testing Recommendations

### Unit Test Targets
- URL parsing with various formats
- Timestamp formatting edge cases (0s, hours, fractional)
- Section type detection
- Timestamp calculation accuracy

### Integration Test Scenarios
- Files with no tags
- Files with various tag formats (TXXX, WPUB, etc.)
- API responses with 0, 1, 2+ sections
- Mix of TrackSection and ChapterSection
- All-null timestamps vs partial timestamps
- Network failures and malformed responses

### Manual Test Cases
1. Large batch with mixed valid/invalid files
2. Verify calculated timestamps spread correctly
3. Unicode handling in artist/song names
4. Very long files (3+ hours)
5. Files with existing LRC (overwrite behavior)

## Known Limitations

1. **No rate limiting**: Rapid batch processing could hit API limits
2. **No retry logic**: Network failures skip the file immediately
3. **Sequential processing**: One file at a time (no parallelization)
4. **No backup**: Overwrites existing LRC files
5. **Strict URL format**: Doesn't normalize URLs (http vs https, www, params)
6. **No logging**: Only console output
7. **Case-sensitive file extension**: Only processes `.mp3`, not `.MP3`

## Future Enhancement Ideas

- **Parallel processing**: Use asyncio/aiohttp for concurrent API requests
- **Rate limiting**: Respect API limits with exponential backoff
- **Retry logic**: Automatic retries for transient failures
- **Progress indicators**: Show progress bar for large batches
- **Logging**: Structured logging to file
- **Backup mode**: Save `.lrc.bak` before overwriting
- **Format support**: Export to SRT, VTT, or other subtitle formats
- **Metadata enhancement**: Pull additional data (description, tags, artwork URLs)
- **URL normalization**: Handle http/https, www/non-www, query parameters
- **Dry run mode**: Preview what would be generated without writing files
- **Smart timestamp adjustment**: Fade-in/fade-out detection for better spacing
