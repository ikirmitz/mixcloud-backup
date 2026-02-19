from pathlib import Path
from mutagen import File
from mutagen.id3 import ID3, USLT

# Import shared utilities
try:
    from .mixcloud_common import extract_lookup, format_lrc_timestamp, fetch_tracklist
except ImportError:
    from mixcloud_common import extract_lookup, format_lrc_timestamp, fetch_tracklist


def generate_lrc_content(username: str, title: str, sections: list[dict]) -> str:
    """
    Generate LRC file content from tracklist sections.
    
    Args:
        username: Mixcloud username (used as artist)
        title: Track title (used as title tag)
        sections: List of section dicts with startSeconds and track/chapter info
    
    Returns:
        Complete LRC file content as string
    """
    lines = []
    lines.append(f"[ar:{username}]")
    lines.append(f"[ti:{title}]")
    lines.append("")  # Blank line after header
    
    for i, s in enumerate(sections, 1):
        if s["__typename"] == "TrackSection":
            track_title = f'{s["artistName"]} – {s["songName"]}'
        else:
            track_title = s.get("chapter", "")
        timestamp = format_lrc_timestamp(s['startSeconds'])
        lines.append(f"{timestamp} {i:02d}. {track_title}")
    
    return "\n".join(lines) + "\n"


def embed_lyrics(mp3_path: Path, lrc_content: str) -> bool:
    """
    Embed LRC content as USLT (unsynchronized lyrics) tag in MP3 file.
    
    Args:
        mp3_path: Path to MP3 file
        lrc_content: LRC content to embed
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Load or create ID3 tags
        try:
            audio = ID3(mp3_path)
        except Exception:
            # File might not have ID3 tags yet
            audio = ID3()
        
        # Remove existing USLT tags to avoid duplicates
        audio.delall('USLT')
        
        # Add new USLT tag
        audio.add(USLT(
            encoding=3,  # UTF-8
            lang='eng',
            desc='',
            text=lrc_content
        ))
        
        audio.save(mp3_path)
        return True
    except Exception as e:
        print(f"  Error embedding lyrics: {e}")
        return False


def process_mp3(mp3_path: Path, embed: bool = True, write_file: bool = False):
    """
    Process an MP3 file to generate LRC content and optionally embed/write it.
    
    Args:
        mp3_path: Path to MP3 file
        embed: If True, embed LRC content as USLT tag (default: True)
        write_file: If True, write .lrc file to disk (default: False)
    """
    if not embed and not write_file:
        return  # Nothing to do
    
    audio = File(mp3_path)
    if audio is None or audio.tags is None:
        print(f"  Skipping (no tags in file)")
        return

    # Get audio duration in seconds
    audio_duration = audio.info.length if hasattr(audio.info, 'length') else None

    tags = audio.tags
    purl = None
    url = None

    # Try different tag formats to find the Mixcloud URL
    # Check for TXXX:purl (ID3v2 user-defined text frame) - most common
    if "TXXX:purl" in tags:
        purl = tags["TXXX:purl"]
        url = str(purl.text[0]) if hasattr(purl, 'text') and purl.text else str(purl)
    # Check for simple 'purl' tag (MP4/M4A format)
    elif "purl" in tags:
        purl = tags["purl"]
        url = str(purl[0]) if isinstance(purl, list) else str(purl)
    # Check for WXXX:purl (ID3v2 user-defined URL frame)
    elif "WXXX:purl" in tags:
        purl = tags["WXXX:purl"]
        url = str(purl.url) if hasattr(purl, 'url') else str(purl)
    # Check for ID3v2 WPUB frame
    elif "WPUB" in tags:
        purl = tags["WPUB"]
        url = str(purl.url) if hasattr(purl, 'url') else str(purl)
    # Check for ID3v2 WOAS frame
    elif "WOAS" in tags:
        purl = tags["WOAS"]
        url = str(purl.url) if hasattr(purl, 'url') else str(purl)
    # Check comment field as fallback
    elif "comment" in tags:
        comment = tags["comment"]
        comment_str = str(comment[0]) if isinstance(comment, list) else str(comment)
        if "mixcloud.com" in comment_str:
            url = comment_str

    if not url:
        print(f"  Skipping (no Mixcloud URL in tags)")
        return
    user, slug = extract_lookup(url)

    if not user or not slug:
        print(f"  Skipping (bad Mixcloud URL format): {url}")
        return

    print(f"  Fetching tracklist for: {user}/{slug}")

    sections = fetch_tracklist(user, slug)
    
    if sections is None:
        print(f"  Skipping (could not fetch tracklist from API)")
        return

    # Count sections (both chapters and tracks) - skip if less than 2
    section_count = len(sections)
    if section_count < 2:
        print(f"  Skipping (only {section_count} section(s) in tracklist)")
        return

    # Count sections with valid timing
    timed_sections = [s for s in sections if s.get('startSeconds') is not None]

    # If no timing info but we have audio duration, calculate evenly-spaced timestamps
    if len(timed_sections) < 2 and audio_duration:
        print(f"  No timing data - calculating evenly-spaced timestamps over {int(audio_duration/60)}:{int(audio_duration%60):02d}")
        interval = audio_duration / len(sections)
        for i, s in enumerate(sections):
            s['startSeconds'] = i * interval
    elif len(timed_sections) < 2:
        print(f"  Skipping (no timing information and no audio duration)")
        return

    # Generate LRC content
    lrc_content = generate_lrc_content(user, mp3_path.stem, sections)
    
    # Track what we did
    actions = []
    
    # Write LRC file if requested
    if write_file:
        lrc_path = mp3_path.with_suffix(".lrc")
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        actions.append(f"wrote {lrc_path.name}")
    
    # Embed lyrics in MP3 if requested
    if embed:
        if embed_lyrics(mp3_path, lrc_content):
            actions.append("embedded")
    
    action_str = " + ".join(actions)
    print(f"  ✓ {action_str} ({section_count} tracks)")


def walk(root, embed: bool = True, write_file: bool = False):
    """
    Recursively process all MP3 files in directory.
    
    Args:
        root: Root directory to process
        embed: If True, embed LRC content as USLT tag (default: True)
        write_file: If True, write .lrc file to disk (default: False)
    """
    for path in Path(root).rglob("*.mp3"):
        try:
            process_mp3(path, embed=embed, write_file=write_file)
        except Exception as e:
            print(f"Error on {path}: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate LRC tracklists from Mixcloud API and embed/save them.'
    )
    parser.add_argument('directory', nargs='?', default='.',
                        help='Directory to process (default: current directory)')
    parser.add_argument('--no-embed', action='store_true',
                        help='Skip embedding lyrics in MP3 USLT tag')
    parser.add_argument('--write-lrc', action='store_true',
                        help='Write separate .lrc files (default: embed only)')
    
    args = parser.parse_args()
    
    embed = not args.no_embed
    write_file = args.write_lrc
    
    if not embed and not write_file:
        print("Nothing to do: both --no-embed and no --write-lrc specified")
    else:
        walk(args.directory, embed=embed, write_file=write_file)
