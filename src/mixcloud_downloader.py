"""
Automated Mixcloud playlist downloader with conditional audio quality.

Downloads all playlists from a Mixcloud account, applying different MP3 quality
settings based on the source audio format:
- webm/opus (newer uploads): -q:a 0 (best quality, ~245 kbps VBR)
- m4a/aac (older uploads): -q:a 2 (medium quality, ~170 kbps VBR)

This avoids upsampling low-quality AAC sources to unnecessarily large MP3 files.
"""

import sys
import argparse
from pathlib import Path

import yt_dlp
from yt_dlp.utils import sanitize_filename

# Import LRC generation from sibling module
# Handle both direct execution and module import
try:
    from .mixcloud_match_to_lrc import process_mp3
    from .mixcloud_common import fetch_user_playlists
except ImportError:
    from mixcloud_match_to_lrc import process_mp3
    from mixcloud_common import fetch_user_playlists


# Shared yt-dlp options for quiet extraction without downloading
_YTDLP_QUIET_OPTS: dict = {
    'quiet': True,
    'no_warnings': True,
}

_YTDLP_FLAT_OPTS: dict = {
    **_YTDLP_QUIET_OPTS,
    'extract_flat': 'in_playlist',
}


def _extract_entries(url: str) -> list[dict]:
    """
    Extract entries from a Mixcloud URL (playlist or user page).
    
    Uses flat extraction mode - doesn't download, just lists contents.
    
    Returns list of entry dicts with 'url', 'title', etc.
    """
    with yt_dlp.YoutubeDL(_YTDLP_FLAT_OPTS) as ydl:
        info = ydl.extract_info(url, download=False)
        if info and 'entries' in info:
            return [e for e in info['entries'] if e]
    return []


def get_user_playlists(username: str) -> list[dict]:
    """
    Get all playlist URLs and titles for a Mixcloud user.
    
    Uses Mixcloud GraphQL API to discover playlists.
    
    Returns list of dicts with 'url' and 'title' keys.
    """
    playlists = fetch_user_playlists(username)
    
    if playlists is None:
        return []
    
    return [
        {
            'url': f"https://www.mixcloud.com/{username}/playlists/{p['slug']}/",
            'title': p['name']
        }
        for p in playlists
    ]


def get_playlist_entries(playlist_url: str) -> list[dict]:
    """
    Get all track entries from a playlist.
    
    Returns list of dicts with track info including 'url'.
    """
    try:
        entries = _extract_entries(playlist_url)
        return [e for e in entries if e.get('url')]
    except Exception as e:
        print(f"Error fetching playlist entries: {e}")
        return []


def fetch_track_info(url: str) -> dict | None:
    """
    Fetch full metadata for a Mixcloud track.
    
    Returns info dict with title, formats, etc. or None on error.
    """
    with yt_dlp.YoutubeDL(_YTDLP_QUIET_OPTS) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"  Warning: Could not fetch track info: {e}")
    return None


def extract_codec_from_info(info: dict | None) -> str:
    """
    Extract audio codec from track info dict.
    
    Returns 'opus' for webm/opus streams, 'aac' for m4a/aac streams,
    or 'unknown' if detection fails.
    """
    if not info:
        return 'unknown'
    
    # Check formats for audio codec
    formats = info.get('formats') or []
    for fmt in formats:
        acodec = fmt.get('acodec', '')
        if acodec and acodec != 'none':
            if 'opus' in acodec.lower():
                return 'opus'
            elif 'aac' in acodec.lower() or 'mp4a' in acodec.lower():
                return 'aac'
    
    # Fallback: check top-level acodec
    acodec = info.get('acodec', '')
    if 'opus' in acodec.lower():
        return 'opus'
    elif 'aac' in acodec.lower() or 'mp4a' in acodec.lower():
        return 'aac'
    
    return 'unknown'


def detect_audio_codec(url: str) -> str:
    """
    Detect the audio codec for a Mixcloud track.
    
    Returns 'opus' for webm/opus streams, 'aac' for m4a/aac streams,
    or 'unknown' if detection fails.
    """
    info = fetch_track_info(url)
    return extract_codec_from_info(info)


def download_track(url: str, output_dir: Path, archive_path: Path, codec: str, playlist_title: str = 'Unknown', info: dict | None = None) -> Path | None:
    """
    Download a single track with quality settings based on codec.
    
    Args:
        url: Mixcloud track URL
        output_dir: Base directory for downloads
        archive_path: Path to download archive file
        codec: Detected codec ('opus', 'aac', or 'unknown')
        playlist_title: Name of the playlist (used in output path)
        info: Track info dict (used to calculate expected path)
    
    Returns:
        Path to MP3 file (downloaded or existing), or None if failed
    """
    # Quality mapping: opus gets best quality, aac gets medium to avoid bloat
    quality = '0' if codec == 'opus' else '2'
    
    # Sanitize playlist title for filesystem (match yt-dlp's sanitization)
    safe_playlist = sanitize_filename(playlist_title)
    
    # Calculate expected MP3 path from info using yt-dlp's sanitization
    expected_path = None
    expected_dir = None
    upload_date = None
    if info:
        uploader = info.get('uploader', 'Unknown')
        upload_date = info.get('upload_date', 'Unknown')
        title = info.get('title', 'Unknown')
        safe_title = sanitize_filename(title)
        expected_dir = output_dir / uploader / safe_playlist
        expected_path = expected_dir / f"{upload_date} - {safe_title}.mp3"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_dir / f'%(uploader)s/{safe_playlist}/%(upload_date)s - %(title)s.%(ext)s'),
        'download_archive': str(archive_path),
        'sleep_interval': 2,
        'max_sleep_interval': 5,
        'ignoreerrors': False,
        'no_warnings': False,
        'extractaudio': True,
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            },
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            },
            {
                'key': 'EmbedThumbnail',
            },
        ],
        'writethumbnail': True,
        'writeinfojson': True,
        # Custom output template for info.json
        'outtmpl_na_placeholder': 'NA',
    }
    
    # Add separate output for infojson
    ydl_opts['outtmpl'] = {
        'default': str(output_dir / f'%(uploader)s/{safe_playlist}/%(upload_date)s - %(title)s.%(ext)s'),
        'infojson': str(output_dir / f'metadata/%(uploader)s/{safe_playlist}/%(upload_date)s - %(title)s.%(ext)s'),
    }
    
    downloaded_file = None
    
    class DownloadLogger:
        def debug(self, msg):
            pass
        
        def warning(self, msg):
            print(f"  Warning: {msg}")
        
        def error(self, msg):
            print(f"  Error: {msg}")
    
    def postprocessor_hook(d):
        nonlocal downloaded_file
        # Capture final filepath after each postprocessor finishes
        if d['status'] == 'finished':
            filepath = d.get('info_dict', {}).get('filepath')
            if filepath and filepath.endswith('.mp3'):
                downloaded_file = Path(filepath)
    
    ydl_opts['logger'] = DownloadLogger()
    ydl_opts['postprocessor_hooks'] = [postprocessor_hook]
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
            # Return the final MP3 path (captured by postprocessor hook)
            if downloaded_file and downloaded_file.exists():
                return downloaded_file
            # If no download happened (skipped/archived), try to find existing file
            if expected_path and expected_path.exists():
                print("  (already exists)")
                return expected_path
            # Fallback: glob for file with matching upload_date prefix
            if expected_dir and expected_dir.exists() and upload_date:
                pattern = f"{upload_date} - *.mp3"
                matches = list(expected_dir.glob(pattern))
                if matches:
                    print(f"  (found existing: {matches[0].name})")
                    return matches[0]
                else:
                    print(f"  (no matching file found for {upload_date})")
        except yt_dlp.utils.DownloadError as e:
            if 'already been recorded' in str(e) or 'has already been downloaded' in str(e).lower():
                print("  (already in archive)")
                # Return expected path if file exists (for LRC generation)
                if expected_path and expected_path.exists():
                    return expected_path
            else:
                print(f"  Download error: {e}")
        except Exception as e:
            print(f"  Unexpected error: {e}")
    
    return None


def download_playlist(playlist_url: str, playlist_title: str, output_dir: Path, archive_path: Path, embed_lyrics: bool = True, write_lrc: bool = False) -> list[Path]:
    """
    Download all tracks from a playlist with conditional quality.
    
    Args:
        embed_lyrics: If True, embed LRC content as USLT tag (default: True)
        write_lrc: If True, write separate .lrc file (default: False)
    
    Returns list of paths to successfully downloaded MP3 files.
    """
    print(f"\n{'='*60}")
    print(f"Playlist: {playlist_title}")
    print(f"URL: {playlist_url}")
    print(f"{'='*60}")
    
    entries = get_playlist_entries(playlist_url)
    
    if not entries:
        print("No tracks found in playlist")
        return []
    
    print(f"Found {len(entries)} tracks\n")
    
    downloaded_files = []
    
    for i, entry in enumerate(entries, 1):
        url = entry.get('url')
        
        # Fetch full track info to get title and codec
        info = fetch_track_info(url)
        title = info.get('title', 'Unknown') if info else 'Unknown'
        codec = extract_codec_from_info(info)
        
        print(f"[{i}/{len(entries)}] {title}")
        quality_desc = "best (opus source)" if codec == 'opus' else "medium (aac source)"
        print(f"  Codec: {codec} → MP3 quality: {quality_desc}")
        
        # Download with appropriate quality
        mp3_path = download_track(url, output_dir, archive_path, codec, playlist_title, info)
        
        if mp3_path and mp3_path.exists():
            downloaded_files.append(mp3_path)
            print(f"  ✓ Ready: {mp3_path}")
            
            # Generate LRC / embed lyrics
            if embed_lyrics or write_lrc:
                print(f"  Processing tracklist...")
                try:
                    process_mp3(mp3_path, embed=embed_lyrics, write_file=write_lrc)
                except Exception as e:
                    print(f"  Tracklist error: {e}")
    
    return downloaded_files


def generate_lrc_files(mp3_files: list[Path]) -> None:
    """
    Generate LRC files for downloaded MP3s using mixcloud_match_to_lrc.
    """
    if not mp3_files:
        print("\nNo MP3 files to generate LRC for.")
        return
    
    print(f"\n{'='*60}")
    print(f"Generating LRC files for {len(mp3_files)} track(s)...")
    print(f"{'='*60}\n")
    
    for mp3_path in mp3_files:
        print(f"Processing: {mp3_path.name}")
        try:
            process_mp3(mp3_path)
        except Exception as e:
            print(f"  LRC error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Download all playlists from a Mixcloud account with conditional audio quality.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s Glastonauts_Live
  %(prog)s Glastonauts_Live --output ~/Music/mixcloud
  %(prog)s Glastonauts_Live --archive ~/my-archive.txt

Quality settings:
  - Opus sources (newer uploads): MP3 VBR quality 0 (~245 kbps)
  - AAC sources (older uploads): MP3 VBR quality 2 (~170 kbps)
""")
    
    parser.add_argument('username', help='Mixcloud username to download playlists from')
    parser.add_argument('--output', '-o', type=Path, default=Path('.'),
                        help='Output directory for downloads (default: current directory)')
    parser.add_argument('--archive', '-a', type=Path,
                        default=Path.home() / 'mixcloud-archive.txt',
                        help='Download archive file to track completed downloads (default: ~/mixcloud-archive.txt)')
    parser.add_argument('--no-embed', action='store_true',
                        help='Skip embedding lyrics in MP3 USLT tag')
    parser.add_argument('--write-lrc', action='store_true',
                        help='Write separate .lrc files (default: embed only)')
    parser.add_argument('--dry-run', action='store_true',
                        help='List playlists without downloading')
    
    args = parser.parse_args()
    
    print(f"Mixcloud Playlist Downloader")
    print(f"Account: {args.username}")
    print(f"Output: {args.output.absolute()}")
    print(f"Archive: {args.archive}")
    print()
    
    # Get all playlists
    print("Fetching playlists...")
    playlists = get_user_playlists(args.username)
    
    if not playlists:
        print(f"No playlists found for user: {args.username}")
        print("Check that the username is correct and the account has public playlists.")
        sys.exit(1)
    
    print(f"Found {len(playlists)} playlists:\n")
    for i, pl in enumerate(playlists, 1):
        print(f"  {i}. {pl['title']}")
    
    if args.dry_run:
        print("\n(Dry run - no downloads performed)")
        sys.exit(0)
    
    # Download each playlist
    all_downloaded = []
    
    embed_lyrics = not args.no_embed
    write_lrc = args.write_lrc
    
    for playlist in playlists:
        downloaded = download_playlist(
            playlist['url'],
            playlist['title'],
            args.output,
            args.archive,
            embed_lyrics=embed_lyrics,
            write_lrc=write_lrc
        )
        all_downloaded.extend(downloaded)
    
    # Summary
    print(f"\n{'='*60}")
    print("Download Complete!")
    print(f"{'='*60}")
    print(f"Playlists processed: {len(playlists)}")
    print(f"Tracks downloaded: {len(all_downloaded)}")
    if embed_lyrics:
        print(f"Lyrics embedded in MP3 tags")
    if write_lrc:
        print(f"LRC files written to disk")
    print(f"Archive file: {args.archive}")


if __name__ == "__main__":
    main()
