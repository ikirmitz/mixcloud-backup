"""
Shared utilities for Mixcloud tools.

Contains common functionality used by both the downloader and LRC generator:
- GraphQL API interaction
- URL parsing
- LRC timestamp formatting
"""

import re
import requests
from urllib.parse import unquote

# Mixcloud GraphQL API endpoint
GRAPHQL_URL = "https://app.mixcloud.com/graphql"

# GraphQL query for fetching tracklist/sections
TRACKLIST_QUERY = """
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


def extract_lookup(url: str) -> tuple[str | None, str | None]:
    """
    Parse a Mixcloud URL to extract username and slug.
    
    Handles URL-encoded characters (e.g., %C3%A6 → æ).
    
    Args:
        url: Mixcloud URL like "https://www.mixcloud.com/user/mix-name/"
    
    Returns:
        Tuple of (username, slug) or (None, None) if URL is invalid
    
    Example:
        >>> extract_lookup("https://www.mixcloud.com/DJ/cool-mix/")
        ("DJ", "cool-mix")
    """
    m = re.search(r"mixcloud\.com/([^/]+)/([^/]+)/?", url)
    if not m:
        return None, None
    # URL-decode the username and slug (handles special characters like æ, ø, etc.)
    return unquote(m.group(1)), unquote(m.group(2))


def format_lrc_timestamp(seconds: float) -> str:
    """
    Convert seconds to LRC timestamp format.
    
    Args:
        seconds: Time in seconds (can be float)
    
    Returns:
        LRC timestamp string like "[01:05.50]"
    
    Example:
        >>> format_lrc_timestamp(65.5)
        "[01:05.50]"
    """
    m = int(seconds // 60)
    s = seconds % 60
    return f"[{m:02d}:{s:05.2f}]"


def fetch_tracklist(username: str, slug: str) -> list[dict] | None:
    """
    Fetch tracklist sections from Mixcloud GraphQL API.
    
    Args:
        username: Mixcloud username
        slug: Cloudcast slug (URL identifier)
    
    Returns:
        List of section dicts with keys like:
        - __typename: "TrackSection" or "ChapterSection"
        - startSeconds: float or None
        - artistName, songName: for TrackSection
        - chapter: for ChapterSection
        
        Returns None if cloudcast not found or API error.
    """
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={
                "query": TRACKLIST_QUERY,
                "variables": {"lookup": {"username": username, "slug": slug}}
            },
            timeout=30
        )
        
        if resp.status_code != 200:
            print(f"API error: HTTP {resp.status_code}")
            return None
        
        data = resp.json()
        cloudcast = data.get("data", {}).get("cloudcastLookup")
        
        if cloudcast is None:
            print(f"Cloudcast not found on Mixcloud: {username}/{slug}")
            return None
        
        return cloudcast.get("sections", [])
    
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return None
