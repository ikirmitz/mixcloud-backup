from pathlib import Path
from mutagen import File
from mutagen.id3 import ID3, USLT
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

# Import shared utilities
try:
    from .mixcloud_common import extract_lookup, format_lrc_timestamp, fetch_tracklist
    from .console import configure_console, get_console
except ImportError:
    from mixcloud_common import extract_lookup, format_lrc_timestamp, fetch_tracklist
    from console import configure_console, get_console


SUPPORTED_AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".opus", ".ogg", ".oga"}


def _get_tag_value(tags, key: str):
    if key in tags:
        return tags[key]
    key_lower = key.lower()
    for tag_key in tags.keys():
        if tag_key.lower() == key_lower:
            return tags[tag_key]
    return None


def _normalize_tag_value(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "url"):
        url_value = value.url
        if isinstance(url_value, (str, bytes)) and url_value:
            return str(url_value)
    if hasattr(value, "text"):
        text = value.text
        if isinstance(text, (list, tuple)) and text:
            return str(text[0])
        return str(text)
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    return str(value)


def extract_mixcloud_url(tags) -> str | None:
    """
    Extract Mixcloud URL from common tag fields.
    """
    for key in ("TXXX:purl", "WXXX:purl", "WPUB", "WOAS"):
        value = _get_tag_value(tags, key)
        url = _normalize_tag_value(value)
        if url and "mixcloud.com" in url:
            return url

    for key in ("purl", "url"):
        value = _get_tag_value(tags, key)
        url = _normalize_tag_value(value)
        if url and "mixcloud.com" in url:
            return url

    comment = _get_tag_value(tags, "comment")
    comment_str = _normalize_tag_value(comment)
    if comment_str and "mixcloud.com" in comment_str:
        return comment_str

    return None


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
        get_console().error(f"  Error embedding lyrics: {e}")
        return False


def embed_lyrics_mp4(m4a_path: Path, lrc_content: str) -> bool:
    """
    Embed LRC content as MP4 lyrics (©lyr) tag in M4A/MP4 file.
    """
    try:
        audio = MP4(m4a_path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["\xa9lyr"] = [lrc_content]
        audio.save()
        return True
    except Exception as e:
        get_console().error(f"  Error embedding MP4 lyrics: {e}")
        return False


def embed_lyrics_ogg_opus(ogg_path: Path, lrc_content: str) -> bool:
    """
    Embed LRC content as Vorbis comment in Ogg/Opus file.
    """
    try:
        audio = OggOpus(ogg_path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["lyrics"] = [lrc_content]
        audio.save()
        return True
    except Exception:
        return False


def embed_lyrics_ogg_vorbis(ogg_path: Path, lrc_content: str) -> bool:
    """
    Embed LRC content as Vorbis comment in Ogg/Vorbis file.
    """
    try:
        audio = OggVorbis(ogg_path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["lyrics"] = [lrc_content]
        audio.save()
        return True
    except Exception as e:
        get_console().error(f"  Error embedding Ogg lyrics: {e}")
        return False


def embed_lyrics_any(audio_path: Path, lrc_content: str) -> bool:
    """
    Embed LRC content based on container type.
    """
    suffix = audio_path.suffix.lower()
    if suffix == ".mp3":
        return embed_lyrics(audio_path, lrc_content)
    if suffix in {".m4a", ".mp4"}:
        return embed_lyrics_mp4(audio_path, lrc_content)
    if suffix in {".opus", ".ogg", ".oga"}:
        if embed_lyrics_ogg_opus(audio_path, lrc_content):
            return True
        return embed_lyrics_ogg_vorbis(audio_path, lrc_content)
    return False


def process_audio_with_url(audio_path: Path, url: str, embed: bool = True, write_file: bool = False):
    """
    Process an audio file when the Mixcloud URL is already known.
    """
    if not embed and not write_file:
        return  # Nothing to do
    console = get_console()
    audio = File(audio_path)
    if audio is None:
        console.warn("  Skipping (unsupported audio format)")
        return
    
    audio_duration = audio.info.length if hasattr(audio.info, 'length') else None
    user, slug = extract_lookup(url)
    
    if not user or not slug:
        console.warn(f"  Skipping (bad Mixcloud URL format): {url}")
        return

    console.info(f"  Fetching tracklist for: {user}/{slug}")
    sections = fetch_tracklist(user, slug)

    if sections is None:
        console.warn("  Skipping (could not fetch tracklist from API)")
        return

    section_count = len(sections)
    if section_count < 2:
        console.warn(f"  Skipping (only {section_count} section(s) in tracklist)")
        return

    timed_sections = [s for s in sections if s.get('startSeconds') is not None]
    if len(timed_sections) < 2 and audio_duration:
        console.info(
            f"  No timing data - calculating evenly-spaced timestamps over "
            f"{int(audio_duration/60)}:{int(audio_duration%60):02d}"
        )
        interval = audio_duration / len(sections)
        for i, s in enumerate(sections):
            s['startSeconds'] = i * interval
    elif len(timed_sections) < 2:
        console.warn("  Skipping (no timing information and no audio duration)")
        return
    
    lrc_content = generate_lrc_content(user, audio_path.stem, sections)
    actions = []
    fallback_write = False
    
    if embed:
        if embed_lyrics_any(audio_path, lrc_content):
            actions.append("embedded")
        else:
            console.warn("  Warning: embedding not supported for this format; writing .lrc instead")
            fallback_write = True
    
    if write_file or fallback_write:
        lrc_path = audio_path.with_suffix(".lrc")
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        actions.append(f"wrote {lrc_path.name}")
    
    action_str = " + ".join(actions)
    console.success(f"  ✓ {action_str} ({section_count} tracks)")


def process_audio_from_tags(audio_path: Path, embed: bool = True, write_file: bool = False):
    """
    Process an audio file by extracting the Mixcloud URL from tags.
    """
    if not embed and not write_file:
        return  # Nothing to do

    console = get_console()

    audio = File(audio_path)
    if audio is None or audio.tags is None:
        console.warn("  Skipping (no tags in file)")
        return

    url = extract_mixcloud_url(audio.tags)
    if not url:
        console.warn("  Skipping (no Mixcloud URL in tags)")
        return

    process_audio_with_url(audio_path, url, embed=embed, write_file=write_file)


def process_mp3(mp3_path: Path, embed: bool = True, write_file: bool = False):
    """
    Process an MP3 file to generate LRC content and optionally embed/write it.
    
    Args:
        mp3_path: Path to MP3 file
        embed: If True, embed LRC content as USLT tag (default: True)
        write_file: If True, write .lrc file to disk (default: False)
    """
    process_audio_from_tags(mp3_path, embed=embed, write_file=write_file)


def walk(root, embed: bool = True, write_file: bool = False):
    """
    Recursively process supported audio files in directory.
    
    Args:
        root: Root directory to process
        embed: If True, embed LRC content as USLT tag (default: True)
        write_file: If True, write .lrc file to disk (default: False)
    """
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_AUDIO_EXTS:
            continue
        try:
            process_audio_from_tags(path, embed=embed, write_file=write_file)
        except Exception as e:
            get_console().error(f"Error on {path}: {e}")


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
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output')
    
    args = parser.parse_args()

    configure_console(no_color=args.no_color)
    
    embed = not args.no_embed
    write_file = args.write_lrc
    
    if not embed and not write_file:
        get_console().warn("Nothing to do: both --no-embed and no --write-lrc specified")
    else:
        walk(args.directory, embed=embed, write_file=write_file)
