"""
Embed existing LRC files into matching audio files as lyrics tags.

Usage:
    uv run python src/embed_lrc.py [directory]
    
This script finds all .lrc files and embeds their contents into
the matching audio file (same name, different extension).

Supported formats: .mp3, .m4a, .mp4, .opus, .ogg, .oga
The original .lrc files are preserved (not deleted).
"""

import argparse
from pathlib import Path

# Import embed function from LRC generator
try:
    from .mixcloud_match_to_lrc import embed_lyrics_any
    from .console import configure_console, get_console
except ImportError:
    from mixcloud_match_to_lrc import embed_lyrics_any
    from console import configure_console, get_console


def _find_matching_audio(lrc_path: Path) -> Path | None:
    base = lrc_path.with_suffix("")
    for ext in (".mp3", ".m4a", ".mp4", ".opus", ".ogg", ".oga"):
        candidate = base.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def embed_lrc_file(lrc_path: Path) -> bool:
    """
    Embed a single LRC file into its matching MP3.
    
    Args:
        lrc_path: Path to .lrc file
    
    Returns:
        True if successful, False otherwise
    """
    audio_path = _find_matching_audio(lrc_path)
    
    if not audio_path:
        get_console().warn(f"  Skipping (no matching audio file): {lrc_path.name}")
        return False
    
    try:
        lrc_content = lrc_path.read_text(encoding="utf-8")
    except Exception as e:
        get_console().error(f"  Error reading LRC: {e}")
        return False
    
    if embed_lyrics_any(audio_path, lrc_content):
        get_console().success(f"  ✓ Embedded: {audio_path.name}")
        return True
    get_console().warn(f"  Skipping (embedding not supported): {audio_path.name}")
    return False


def walk(root: str) -> tuple[int, int]:
    """
    Recursively embed all LRC files in directory.
    
    Args:
        root: Root directory to process
    
    Returns:
        Tuple of (processed_count, success_count)
    """
    processed = 0
    success = 0
    
    for lrc_path in Path(root).rglob("*.lrc"):
        processed += 1
        get_console().info(f"Processing: {lrc_path}")
        if embed_lrc_file(lrc_path):
            success += 1
    
    return processed, success


def main():
    parser = argparse.ArgumentParser(
        description='Embed existing LRC files into matching audio files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     # Process current directory
  %(prog)s ~/Music/Mixcloud    # Process specific directory

Note: Original .lrc files are preserved (not deleted).
"""
    )
    
    parser.add_argument('directory', nargs='?', default='.',
                        help='Directory to process (default: current directory)')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output')
    
    args = parser.parse_args()

    configure_console(no_color=args.no_color)
    console = get_console()
    console.rule("Embedding LRC files as lyrics tags")
    console.print(f"Directory: {Path(args.directory).resolve()}")
    console.print()
    
    processed, success = walk(args.directory)
    
    console.print()
    summary_rows = [
        ("Processed", f"{processed} LRC files"),
        ("Embedded", f"{success} files"),
    ]
    if processed > success:
        summary_rows.append(("Skipped", f"{processed - success} files"))
    console.summary_table("Summary", summary_rows)


if __name__ == "__main__":
    main()
