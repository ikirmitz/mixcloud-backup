"""
Find and optionally download orphan Mixcloud tracks.

Orphan tracks are uploads that don't belong to any playlist.

Usage:
    uv run python src/mixcloud_orphans.py USERNAME [options]
    
Options:
    --download      Download orphan tracks (default: just list them)
    --output, -o    Output directory for downloads
    --archive, -a   Archive file to track downloads
    --to-mp3        Transcode audio to MP3 (default: keep original container)
    --no-embed      Skip embedding lyrics in MP3 tags
    --write-lrc     Write separate .lrc files
"""

import argparse
import sys
from pathlib import Path

# Import shared utilities
try:
    from .mixcloud_common import (
        fetch_user_playlists,
        fetch_user_uploads,
        fetch_playlist_items,
    )
    from .console import configure_console, get_console
except ImportError:
    from mixcloud_common import (
        fetch_user_playlists,
        fetch_user_uploads,
        fetch_playlist_items,
    )
    from console import configure_console, get_console


def find_orphan_tracks(username: str) -> tuple[list[dict], list[dict], set[str]] | None:
    """
    Find tracks that don't belong to any playlist.
    
    Args:
        username: Mixcloud username
    
    Returns:
        Tuple of (all_uploads, orphan_tracks, playlist_slugs) or None on error
        - all_uploads: List of all upload dicts
        - orphan_tracks: List of upload dicts not in any playlist
        - playlist_slugs: Set of slugs that are in playlists
    """
    console = get_console()
    console.info(f"Fetching playlists for {username}...")
    playlists = fetch_user_playlists(username)
    if playlists is None:
        return None
    console.info(f"  Found {len(playlists)} playlists")
    
    # Collect all tracks from all playlists
    playlist_slugs = set()
    for i, playlist in enumerate(playlists, 1):
        console.print(f"  [{i}/{len(playlists)}] Fetching items from '{playlist['name']}'...")
        items = fetch_playlist_items(username, playlist['slug'])
        if items:
            for item in items:
                playlist_slugs.add(item['slug'])
    
    console.info(f"  Total tracks in playlists: {len(playlist_slugs)}")
    
    # Get all uploads
    console.info(f"Fetching all uploads for {username}...")
    all_uploads = fetch_user_uploads(username)
    if all_uploads is None:
        return None
    console.info(f"  Found {len(all_uploads)} uploads")
    
    # Find orphans (uploads not in any playlist)
    orphan_tracks = [
        upload for upload in all_uploads
        if upload['slug'] not in playlist_slugs
    ]
    
    return all_uploads, orphan_tracks, playlist_slugs


def main():
    parser = argparse.ArgumentParser(
        description='Find and optionally download orphan Mixcloud tracks.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s Glastonauts_Live                    # List orphan tracks
  %(prog)s Glastonauts_Live --download         # Download orphan tracks
  %(prog)s Glastonauts_Live --download -o ~/Music/orphans
"""
    )
    
    parser.add_argument('username', help='Mixcloud username to check')
    parser.add_argument('--download', action='store_true',
                        help='Download orphan tracks (default: just list them)')
    parser.add_argument('--output', '-o', type=Path, default=Path('.'),
                        help='Output directory for downloads (default: current directory)')
    parser.add_argument('--archive', '-a', type=Path,
                        default=Path.home() / 'mixcloud-archive.txt',
                        help='Download archive file (default: ~/mixcloud-archive.txt)')
    parser.add_argument('--to-mp3', action='store_true',
                        help='Transcode audio to MP3 (default: keep original container)')
    parser.add_argument('--no-embed', action='store_true',
                        help='Skip embedding lyrics in MP3 USLT tag')
    parser.add_argument('--write-lrc', action='store_true',
                        help='Write separate .lrc files (default: embed only)')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output')
    
    args = parser.parse_args()

    configure_console(no_color=args.no_color)
    console = get_console()
    console.rule("Mixcloud Orphan Track Finder")
    console.print(f"Account: {args.username}")
    console.print()
    
    result = find_orphan_tracks(args.username)
    if result is None:
        console.error("Error fetching data from Mixcloud")
        sys.exit(1)
    
    all_uploads, orphan_tracks, playlist_slugs = result
    
    # Summary
    console.summary_table(
        "Summary",
        [
            ("Total uploads", str(len(all_uploads))),
            ("In playlists", str(len(playlist_slugs))),
            ("Orphans", str(len(orphan_tracks))),
        ],
    )
    
    if not orphan_tracks:
        console.info("No orphan tracks found - all uploads are in playlists!")
        sys.exit(0)
    
    # List orphans
    orphan_rows = []
    for i, track in enumerate(orphan_tracks, 1):
        url = track.get('url') or f"https://www.mixcloud.com/{track.get('owner_username') or args.username}/{track['slug']}/"
        orphan_rows.append((i, track['name'], url))
    console.table("Orphan Tracks", ["No", "Title", "URL"], orphan_rows)
    
    if not args.download:
        console.info(f"Use --download to download these {len(orphan_tracks)} tracks")
        sys.exit(0)
    
    # Download orphan tracks
    console.rule("Downloading Orphan Tracks")
    
    # Import downloader functions
    try:
        from .mixcloud_downloader import (
            fetch_track_info,
            extract_codec_from_info,
            download_track,
        )
        from .mixcloud_match_to_lrc import process_mp3, process_audio_with_url
    except ImportError:
        from mixcloud_downloader import (
            fetch_track_info,
            extract_codec_from_info,
            download_track,
        )
        from mixcloud_match_to_lrc import process_mp3, process_audio_with_url
    
    downloaded_files = []
    
    for i, track in enumerate(orphan_tracks, 1):
        url = track.get('url') or f"https://www.mixcloud.com/{track.get('owner_username') or args.username}/{track['slug']}/"
        
        # Fetch full track info
        info = fetch_track_info(url)
        title = info.get('title', track['name']) if info else track['name']
        codec = extract_codec_from_info(info) if args.to_mp3 else 'unknown'
        
        console.print(f"[{i}/{len(orphan_tracks)}] {title}")
        if args.to_mp3:
            quality_desc = "best (opus source)" if codec == 'opus' else "medium (aac source)"
            console.print(f"  Codec: {codec} → MP3 quality: {quality_desc}")
        else:
            console.print("  Audio: keeping original audio")
        
        # Download with "Orphans" as playlist name
        mp3_path = download_track(url, args.output, args.archive, codec, "Orphans", info, to_mp3=args.to_mp3)
        
        if mp3_path and mp3_path.exists():
            downloaded_files.append(mp3_path)
            console.success(f"  ✓ Ready: {mp3_path}")
            
            # Process tracklist (embed/write LRC)
            embed_lyrics = not args.no_embed
            write_lrc = args.write_lrc
            if embed_lyrics or write_lrc:
                console.info("  Processing tracklist...")
                try:
                    process_audio_with_url(mp3_path, url, embed=embed_lyrics, write_file=write_lrc)
                except Exception as e:
                    console.error(f"  Tracklist error: {e}")
    
    # Final summary
    console.summary_table(
        "Download Complete",
        [
            ("Orphan tracks found", str(len(orphan_tracks))),
            ("Tracks downloaded", str(len(downloaded_files))),
            ("Archive file", str(args.archive)),
        ],
    )


if __name__ == "__main__":
    main()
