"""
Automated Mixcloud downloader with optional playlist organization.

Defaults to downloading all uploads without transcoding. Use --playlists to
organize by playlist, and --to-mp3 to transcode to MP3 with quality settings
based on the source audio format:
- webm/opus (newer uploads): -q:a 0 (best quality, ~245 kbps VBR)
- m4a/aac (older uploads): -q:a 2 (medium quality, ~170 kbps VBR)

This avoids upsampling low-quality AAC sources to unnecessarily large MP3 files.
"""

import sys
import argparse
from pathlib import Path
from datetime import date

import yt_dlp
from yt_dlp.utils import sanitize_filename

# Import LRC generation from sibling module
# Handle both direct execution and module import
try:
    from .mixcloud_match_to_lrc import process_mp3, process_audio_with_url
    from .mixcloud_common import fetch_user_playlists, fetch_user_uploads
    from .console import configure_console, get_console
except ImportError:
    from mixcloud_match_to_lrc import process_mp3, process_audio_with_url
    from mixcloud_common import fetch_user_playlists, fetch_user_uploads
    from console import configure_console, get_console


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


def get_user_uploads(username: str) -> list[dict]:
    """
    Get all upload URLs and titles for a Mixcloud user.
    
    Uses Mixcloud GraphQL API to discover uploads.
    
    Returns list of dicts with 'url' and 'title' keys.
    """
    uploads = fetch_user_uploads(username)
    
    if uploads is None:
        return []
    
    return [
        {
            'url': u.get('url') or f"https://www.mixcloud.com/{u.get('owner_username') or username}/{u['slug']}/",
            'title': u['name']
        }
        for u in uploads
    ]


def _parse_since_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        parts = value.split("-")
        if len(parts) != 3:
            raise ValueError
        year, month, day = (int(p) for p in parts)
        return date(year, month, day)
    except ValueError:
        get_console().warn(f"Invalid --since date format: {value} (expected YYYY-MM-DD)")
        return None


def _is_older_than(info: dict | None, since_date: date | None) -> bool:
    if not since_date or not info:
        return False
    upload_date = info.get('upload_date')
    if not upload_date:
        get_console().warn("  Warning: No upload_date available; skipping --since filter")
        return False
    try:
        year = int(upload_date[0:4])
        month = int(upload_date[4:6])
        day = int(upload_date[6:8])
        return date(year, month, day) < since_date
    except ValueError:
        get_console().warn("  Warning: Invalid upload_date; skipping --since filter")
        return False


def get_playlist_entries(playlist_url: str) -> list[dict]:
    """
    Get all track entries from a playlist.
    
    Returns list of dicts with track info including 'url'.
    """
    try:
        entries = _extract_entries(playlist_url)
        return [e for e in entries if e.get('url')]
    except Exception as e:
        get_console().error(f"Error fetching playlist entries: {e}")
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
            get_console().warn(f"  Warning: Could not fetch track info: {e}")
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


def download_track(url: str, output_dir: Path, archive_path: Path, codec: str, playlist_title: str = 'Unknown', info: dict | None = None, to_mp3: bool = False) -> Path | None:
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
        Path to audio file (downloaded or existing), or None if failed
    """
    console = get_console()

    # Quality mapping: opus gets best quality, aac gets medium to avoid bloat
    quality = '0' if codec == 'opus' else '2'
    
    # Sanitize playlist title for filesystem (match yt-dlp's sanitization)
    safe_playlist = sanitize_filename(playlist_title)
    
    # Calculate expected path from info using yt-dlp's sanitization
    expected_path = None
    expected_dir = None
    upload_date = None
    if info:
        uploader = info.get('uploader', 'Unknown')
        upload_date = info.get('upload_date', 'Unknown')
        title = info.get('title', 'Unknown')
        safe_title = sanitize_filename(title)
        expected_dir = output_dir / uploader / safe_playlist
        ext = 'mp3' if to_mp3 else info.get('ext', 'audio')
        expected_path = expected_dir / f"{upload_date} - {safe_title}.{ext}"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_dir / f'%(uploader)s/{safe_playlist}/%(upload_date)s - %(title)s.%(ext)s'),
        'download_archive': str(archive_path),
        'sleep_interval': 2,
        'max_sleep_interval': 5,
        'ignoreerrors': False,
        'no_warnings': False,
        'writeinfojson': True,
        # Custom output template for info.json
        'outtmpl_na_placeholder': 'NA',
    }
    
    # Add separate output for infojson
    ydl_opts['outtmpl'] = {
        'default': str(output_dir / f'%(uploader)s/{safe_playlist}/%(upload_date)s - %(title)s.%(ext)s'),
        'infojson': str(output_dir / f'metadata/%(uploader)s/{safe_playlist}/%(upload_date)s - %(title)s.%(ext)s'),
    }
    
    if to_mp3:
        ydl_opts['extractaudio'] = True
        ydl_opts['postprocessors'] = [
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
        ]
        ydl_opts['writethumbnail'] = True
    else:
        ydl_opts['extractaudio'] = True
        ydl_opts['postprocessors'] = [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'best',
            },
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            },
            {
                'key': 'EmbedThumbnail',
            },
        ]
        ydl_opts['writethumbnail'] = True
    
    downloaded_file = None
    
    class DownloadLogger:
        def debug(self, msg):
            pass
        
        def warning(self, msg):
            console.warn(f"  Warning: {msg}")
        
        def error(self, msg):
            console.error(f"  Error: {msg}")
    
    def postprocessor_hook(d):
        nonlocal downloaded_file
        # Capture final filepath after each postprocessor finishes
        if d['status'] == 'finished':
            filepath = d.get('info_dict', {}).get('filepath')
            if filepath:
                downloaded_file = Path(filepath)
    
    ydl_opts['logger'] = DownloadLogger()
    ydl_opts['postprocessor_hooks'] = [postprocessor_hook]
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
            # Return the final path (captured by postprocessor hook)
            if downloaded_file and downloaded_file.exists():
                return downloaded_file
            # If no download happened (skipped/archived), try to find existing file
            if expected_path and expected_path.exists():
                console.info("  (already exists)")
                return expected_path
            # Fallback: glob for file with matching upload_date prefix
            if expected_dir and expected_dir.exists() and upload_date:
                pattern = f"{upload_date} - *"
                matches = list(expected_dir.glob(pattern))
                if matches:
                    console.info(f"  (found existing: {matches[0].name})")
                    return matches[0]
                else:
                    console.warn(f"  (no matching file found for {upload_date})")
        except yt_dlp.utils.DownloadError as e:
            if 'already been recorded' in str(e) or 'has already been downloaded' in str(e).lower():
                console.info("  (already in archive)")
                # Return expected path if file exists (for LRC generation)
                if expected_path and expected_path.exists():
                    return expected_path
            else:
                console.error(f"  Download error: {e}")
        except Exception as e:
            console.error(f"  Unexpected error: {e}")
    
    return None


def download_playlist(playlist_url: str, playlist_title: str, output_dir: Path, archive_path: Path, embed_lyrics: bool = True, write_lrc: bool = False, to_mp3: bool = False, limit: int | None = None, since_date: date | None = None) -> list[Path]:
    """
    Download all tracks from a playlist with conditional quality.
    
    Args:
        embed_lyrics: If True, embed LRC content as USLT tag (default: True)
        write_lrc: If True, write separate .lrc file (default: False)
    
    Returns list of paths to successfully downloaded audio files.
    """
    console = get_console()
    console.rule(f"Playlist: {playlist_title}")
    console.print(f"URL: {playlist_url}")
    
    entries = get_playlist_entries(playlist_url)
    
    if not entries:
        console.warn("No tracks found in playlist")
        return []
    
    console.info(f"Found {len(entries)} tracks")
    console.print()
    
    downloaded_files = []
    
    processed = 0
    for i, entry in enumerate(entries, 1):
        url = entry.get('url')
        if not url:
            continue
        
        # Fetch full track info to get title and codec
        info = fetch_track_info(url)
        title = info.get('title', 'Unknown') if info else 'Unknown'
        if _is_older_than(info, since_date):
            console.print(f"[{i}/{len(entries)}] {title}")
            console.warn("  Skipping (before --since date)")
            continue
        
        codec = extract_codec_from_info(info) if to_mp3 else 'unknown'
        
        console.print(f"[{i}/{len(entries)}] {title}")
        if to_mp3:
            quality_desc = "best (opus source)" if codec == 'opus' else "medium (aac source)"
            console.print(f"  Codec: {codec} → MP3 quality: {quality_desc}")
        else:
            console.print("  Audio: keeping original audio")
        
        # Download with appropriate settings
        audio_path = download_track(url, output_dir, archive_path, codec, playlist_title, info, to_mp3=to_mp3)
        
        if audio_path and audio_path.exists():
            downloaded_files.append(audio_path)
            console.success(f"  ✓ Ready: {audio_path}")
            
            # Generate LRC / embed lyrics
            if embed_lyrics or write_lrc:
                console.info("  Processing tracklist...")
                try:
                    process_audio_with_url(audio_path, url, embed=embed_lyrics, write_file=write_lrc)
                except Exception as e:
                    console.error(f"  Tracklist error: {e}")
        
        processed += 1
        if limit and processed >= limit:
            console.warn(f"Reached --limit {limit}; stopping")
            break
    
    return downloaded_files


def generate_lrc_files(mp3_files: list[Path]) -> None:
    """
    Generate LRC files for downloaded MP3s using mixcloud_match_to_lrc.
    """
    console = get_console()
    if not mp3_files:
        console.warn("No MP3 files to generate LRC for.")
        return
    
    console.rule(f"Generating LRC files for {len(mp3_files)} track(s)")
    console.print()
    
    for mp3_path in mp3_files:
        console.info(f"Processing: {mp3_path.name}")
        try:
            process_mp3(mp3_path)
        except Exception as e:
            console.error(f"  LRC error: {e}")


def main():
    parser = argparse.ArgumentParser(
                description='Download Mixcloud uploads or playlists with optional MP3 transcoding.',
                formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog="""
Examples:
    %(prog)s Glastonauts_Live
    %(prog)s Glastonauts_Live --playlists
    %(prog)s Glastonauts_Live --to-mp3
    %(prog)s Glastonauts_Live --limit 50 --since 2024-01-01

Transcoding (optional):
    - Opus sources (newer uploads): MP3 VBR quality 0 (~245 kbps)
    - AAC sources (older uploads): MP3 VBR quality 2 (~170 kbps)
""")

    parser.add_argument('username', help='Mixcloud username to download from')
    parser.add_argument('--output', '-o', type=Path, default=Path('.'),
                        help='Output directory for downloads (default: current directory)')
    parser.add_argument('--archive', '-a', type=Path,
                        default=Path.home() / 'mixcloud-archive.txt',
                        help='Download archive file to track completed downloads (default: ~/mixcloud-archive.txt)')
    parser.add_argument('--playlists', action='store_true',
                        help='Download by playlist (default: all uploads)')
    parser.add_argument('--to-mp3', action='store_true',
                        help='Transcode audio to MP3 (default: keep original container)')
    parser.add_argument('--no-embed', action='store_true',
                        help='Skip embedding lyrics in MP3 USLT tag')
    parser.add_argument('--write-lrc', action='store_true',
                        help='Write separate .lrc files (default: embed only)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of tracks to download')
    parser.add_argument('--since', type=str, default=None,
                        help='Only download uploads on/after this date (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true',
                        help='List playlists without downloading')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output')
    
    args = parser.parse_args()

    configure_console(no_color=args.no_color)
    console = get_console()

    console.rule("Mixcloud Downloader")
    console.print(f"Account: {args.username}")
    console.print(f"Output: {args.output.absolute()}")
    console.print(f"Archive: {args.archive}")
    console.print()
    
    since_date = _parse_since_date(args.since)
    
    embed_lyrics = not args.no_embed
    write_lrc = args.write_lrc
    to_mp3 = args.to_mp3
    
    all_downloaded = []
    
    processed_uploads = 0
    
    if args.playlists:
        console.info("Fetching playlists...")
        playlists = get_user_playlists(args.username)
        
        if not playlists:
            console.error(f"No playlists found for user: {args.username}")
            console.print("Check that the username is correct and the account has public playlists.")
            sys.exit(1)
        
        console.info(f"Found {len(playlists)} playlists")
        playlist_rows = [(i, pl['title']) for i, pl in enumerate(playlists, 1)]
        console.table("Playlists", ["No", "Title"], playlist_rows)
        
        if args.dry_run:
            total_shown = 0
            rows = []
            for i, playlist in enumerate(playlists, 1):
                if args.limit is not None and total_shown >= args.limit:
                    break
                console.info(f"Scanning playlist {i}/{len(playlists)}: {playlist['title']}")
                entries = get_playlist_entries(playlist['url'])
                if not entries:
                    console.warn("  No tracks found in playlist")
                    continue
                if since_date:
                    console.info(f"  Applying --since {since_date}")
                processed_entries = 0
                matched_entries = 0
                for entry in entries:
                    if args.limit is not None and total_shown >= args.limit:
                        break
                    url = entry.get('url')
                    if not url:
                        continue
                    processed_entries += 1
                    info = fetch_track_info(url)
                    title = info.get('title', entry.get('title', 'Unknown')) if info else entry.get('title', 'Unknown')
                    if _is_older_than(info, since_date):
                        continue
                    total_shown += 1
                    matched_entries += 1
                    rows.append((total_shown, playlist['title'], title))
                console.info(f"  Matched {matched_entries} of {processed_entries} tracks")
            if rows:
                console.table("Dry Run Tracks", ["No", "Playlist", "Title"], rows)
            else:
                console.warn("No tracks matched dry run filters")
            if args.limit is not None and total_shown >= args.limit:
                console.warn(f"Reached --limit {args.limit} for dry run")
            console.info("Dry run - no downloads performed")
            sys.exit(0)
        
        for playlist in playlists:
            remaining = None
            if args.limit is not None:
                remaining = max(args.limit - len(all_downloaded), 0)
                if remaining == 0:
                    break
            downloaded = download_playlist(
                playlist['url'],
                playlist['title'],
                args.output,
                args.archive,
                embed_lyrics=embed_lyrics,
                write_lrc=write_lrc,
                to_mp3=to_mp3,
                limit=remaining,
                since_date=since_date
            )
            all_downloaded.extend(downloaded)
    else:
        console.info("Fetching uploads...")
        uploads = get_user_uploads(args.username)
        
        if not uploads:
            console.error(f"No uploads found for user: {args.username}")
            console.print("Check that the username is correct and the account has public uploads.")
            sys.exit(1)
        
        console.info(f"Found {len(uploads)} uploads")
        
        if args.dry_run:
            shown = 0
            rows = []
            if since_date:
                console.info(f"Applying --since {since_date}")
            for i, up in enumerate(uploads, 1):
                if args.limit is not None and shown >= args.limit:
                    break
                url = up.get('url')
                if not url:
                    continue
                if since_date:
                    info = fetch_track_info(url)
                    if _is_older_than(info, since_date):
                        continue
                shown += 1
                rows.append((shown, up['title']))
                if shown % 25 == 0:
                    console.info(f"Matched {shown} uploads so far")
            if rows:
                console.table("Dry Run Uploads", ["No", "Title"], rows)
            else:
                console.warn("No uploads matched dry run filters")
            if args.limit is not None and shown >= args.limit:
                console.warn(f"Reached --limit {args.limit} for dry run")
            console.info("Dry run - no downloads performed")
            sys.exit(0)
        
        processed = 0
        for i, up in enumerate(uploads, 1):
            url = up.get('url')
            if not url:
                continue
            
            info = fetch_track_info(url)
            title = info.get('title', up['title']) if info else up['title']
            if _is_older_than(info, since_date):
                console.print(f"[{i}/{len(uploads)}] {title}")
                console.warn("  Skipping (before --since date)")
                continue
            
            codec = extract_codec_from_info(info) if to_mp3 else 'unknown'
            
            console.print(f"[{i}/{len(uploads)}] {title}")
            if to_mp3:
                quality_desc = "best (opus source)" if codec == 'opus' else "medium (aac source)"
                console.print(f"  Codec: {codec} → MP3 quality: {quality_desc}")
            else:
                console.print("  Audio: keeping original audio")
            
            audio_path = download_track(url, args.output, args.archive, codec, "Uploads", info, to_mp3=to_mp3)
            
            if audio_path and audio_path.exists():
                all_downloaded.append(audio_path)
                console.success(f"  ✓ Ready: {audio_path}")
                
                if embed_lyrics or write_lrc:
                    console.info("  Processing tracklist...")
                    try:
                        process_audio_with_url(audio_path, url, embed=embed_lyrics, write_file=write_lrc)
                    except Exception as e:
                        console.error(f"  Tracklist error: {e}")
            
            processed += 1
            processed_uploads = processed
            if args.limit and processed >= args.limit:
                console.warn(f"Reached --limit {args.limit}; stopping")
                break
    
    # Summary
    summary_rows = []
    if args.playlists:
        summary_rows.append(("Playlists processed", str(len(playlists))))
    else:
        summary_rows.append(("Uploads processed", str(processed_uploads)))
    summary_rows.append(("Tracks downloaded", str(len(all_downloaded))))
    if embed_lyrics:
        summary_rows.append(("Lyrics", "Embedded when supported; .lrc written for other formats"))
    if write_lrc:
        summary_rows.append(("LRC files", "Written to disk"))
    summary_rows.append(("Archive file", str(args.archive)))
    console.summary_table("Download Complete", summary_rows)


if __name__ == "__main__":
    main()
