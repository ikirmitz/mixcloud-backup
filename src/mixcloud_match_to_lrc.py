import os
import re
import json
import requests
from pathlib import Path
from mutagen.id3 import ID3

GRAPHQL_URL = "https://www.mixcloud.com/graphql"

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
    m = re.search(r"mixcloud\\.com/([^/]+)/([^/]+)/?", url)
    if not m:
        return None, None
    return m.group(1), m.group(2)

def fmt(sec):
    m = int(sec // 60)
    s = sec % 60
    return f"[{m:02d}:{s:05.2f}]"

def process_mp3(mp3_path: Path):
    tags = ID3(mp3_path)
    purl = tags.get("WPUB") or tags.get("WOAS") or tags.get("WXXX:purl")

    if not purl:
        print(f"Skipping (no podcast URL): {mp3_path}")
        return

    url = str(purl.url)
    user, slug = extract_lookup(url)

    if not user or not slug:
        print(f"Bad Mixcloud URL: {url}")
        return

    print(f"Fetching tracklist for: {user}/{slug}")

    resp = requests.post(GRAPHQL_URL, json={
        "query": QUERY,
        "variables": {"lookup": {"username": user, "slug": slug}}
    })

    data = resp.json()
    sections = data["data"]["cloudcastLookup"]["sections"]

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
