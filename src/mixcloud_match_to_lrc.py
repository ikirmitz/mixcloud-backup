import os
import re
import json
import requests
from pathlib import Path
from mutagen import File
from urllib.parse import unquote

GRAPHQL_URL = "https://app.mixcloud.com/graphql"

QUERY = """
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
"""

def extract_lookup(url: str):
    m = re.search(r"mixcloud\.com/([^/]+)/([^/]+)/?", url)
    if not m:
        return None, None
    # URL-decode the username and slug (handles special characters like æ, ø, etc.)
    return unquote(m.group(1)), unquote(m.group(2))

def fmt(sec):
    m = int(sec // 60)
    s = sec % 60
    return f"[{m:02d}:{s:05.2f}]"

def process_mp3(mp3_path: Path):
    audio = File(mp3_path)
    if audio is None or audio.tags is None:
        print(f"Skipping (no tags): {mp3_path}")
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
        print(f"Skipping (no podcast URL): {mp3_path}")
        return
    user, slug = extract_lookup(url)

    if not user or not slug:
        print(f"Bad Mixcloud URL: {url}")
        return

    print(f"Fetching tracklist for: {user}/{slug}")

    resp = requests.post(GRAPHQL_URL, json={
        "query": QUERY,
        "variables": {"lookup": {"username": user, "slug": slug}}
    })

    if resp.status_code != 200:
        print(f"API error: HTTP {resp.status_code}")
        return

    data = resp.json()
    cloudcast = data.get("data", {}).get("cloudcastLookup")
    
    if cloudcast is None:
        print(f"Cloudcast not found on Mixcloud: {user}/{slug}")
        return
    
    sections = cloudcast["sections"]

    # Count sections (both chapters and tracks) - skip if less than 2
    section_count = len(sections)
    if section_count < 2:
        print(f"Skipping (only {section_count} section(s)): {mp3_path}")
        return

    # Count sections with valid timing
    timed_sections = [s for s in sections if s.get('startSeconds') is not None]

    # If no timing info but we have audio duration, calculate evenly-spaced timestamps
    if len(timed_sections) < 2 and audio_duration:
        print(f"No timing data - calculating evenly-spaced timestamps over {int(audio_duration/60)}:{int(audio_duration%60):02d}")
        interval = audio_duration / len(sections)
        for i, s in enumerate(sections):
            s['startSeconds'] = i * interval
    elif len(timed_sections) < 2:
        print(f"Skipping (no timing information and no audio duration): {mp3_path}")
        return

    lrc_path = mp3_path.with_suffix(".lrc")

    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(f"[ar:{user}]\n")
        f.write(f"[ti:{mp3_path.stem}]\n\n")

        for s in sections:
            if s["__typename"] == "TrackSection":
                title = f'{s["artistName"]} – {s["songName"]}'
            else:
                title = s.get("chapter", "")
            f.write(f"{fmt(s['startSeconds'])} {title}\n")

    print(f"✓ Wrote {lrc_path}")

def walk(root):
    for path in Path(root).rglob("*.mp3"):
        try:
            process_mp3(path)
        except Exception as e:
            print(f"Error on {path}: {e}")

if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    walk(root)
