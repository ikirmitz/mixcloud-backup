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

# GraphQL query for fetching user playlists
USER_PLAYLISTS_QUERY = """
query UserPlaylists($lookup: UserLookup!, $first: Int!, $after: String) {
  userLookup(lookup: $lookup) {
    playlists(first: $first, after: $after, orderBy: ALPHABETICAL) {
      edges {
        node {
          name
          slug
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

# GraphQL query for fetching all user uploads
USER_UPLOADS_QUERY = """
query UserUploads($lookup: UserLookup!, $first: Int!, $after: String) {
  userLookup(lookup: $lookup) {
    uploads(first: $first, after: $after) {
      edges {
        node {
          name
          slug
                    url
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

# GraphQL query for fetching playlist items (tracks in a playlist)
PLAYLIST_ITEMS_QUERY = """
query PlaylistItems($lookup: PlaylistLookup!, $first: Int!, $after: String) {
  playlistLookup(lookup: $lookup) {
    items(first: $first, after: $after) {
      edges {
        node {
          cloudcast {
            name
            slug
          }
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
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


def fetch_user_playlists(username: str) -> list[dict] | None:
    """
    Fetch all playlists for a Mixcloud user via GraphQL API.
    
    Handles pagination automatically to retrieve all playlists.
    
    Args:
        username: Mixcloud username
    
    Returns:
        List of playlist dicts with keys:
        - name: Playlist display name
        - slug: URL slug for the playlist
        
        Returns None if user not found or API error.
    """
    all_playlists = []
    after_cursor = None
    
    try:
        while True:
            resp = requests.post(
                GRAPHQL_URL,
                json={
                    "query": USER_PLAYLISTS_QUERY,
                    "variables": {
                        "lookup": {"username": username},
                        "first": 50,
                        "after": after_cursor
                    }
                },
                headers={
                    "origin": "https://www.mixcloud.com",
                    "referer": "https://www.mixcloud.com/"
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                print(f"API error: HTTP {resp.status_code}")
                return None
            
            data = resp.json()
            user_data = data.get("data", {}).get("userLookup")
            
            if user_data is None:
                print(f"User not found on Mixcloud: {username}")
                return None
            
            playlists_data = user_data.get("playlists", {})
            edges = playlists_data.get("edges", [])
            
            for edge in edges:
                node = edge.get("node", {})
                all_playlists.append({
                    "name": node.get("name", "Unknown"),
                    "slug": node.get("slug", "")
                })
            
            # Check for more pages
            page_info = playlists_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                after_cursor = page_info.get("endCursor")
            else:
                break
        
        return all_playlists
    
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return None


def fetch_user_uploads(username: str) -> list[dict] | None:
    """
    Fetch all uploads (cloudcasts) for a Mixcloud user via GraphQL API.
    
    Handles pagination automatically to retrieve all uploads.
    
    Args:
        username: Mixcloud username
    
    Returns:
        List of upload dicts with keys:
        - name: Upload title
        - slug: URL slug for the upload
        
        Returns None if user not found or API error.
    """
    all_uploads = []
    after_cursor = None
    
    try:
        while True:
            resp = requests.post(
                GRAPHQL_URL,
                json={
                    "query": USER_UPLOADS_QUERY,
                    "variables": {
                        "lookup": {"username": username},
                        "first": 50,
                        "after": after_cursor
                    }
                },
                headers={
                    "origin": "https://www.mixcloud.com",
                    "referer": "https://www.mixcloud.com/"
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                print(f"API error: HTTP {resp.status_code}")
                return None
            
            data = resp.json()
            user_data = data.get("data", {}).get("userLookup")
            
            if user_data is None:
                print(f"User not found on Mixcloud: {username}")
                return None
            
            uploads_data = user_data.get("uploads", {})
            edges = uploads_data.get("edges", [])
            
            for edge in edges:
                node = edge.get("node", {})
                all_uploads.append({
                    "name": node.get("name", "Unknown"),
                    "slug": node.get("slug", ""),
                    "url": node.get("url"),
                    "owner_username": None,
                })
            
            # Check for more pages
            page_info = uploads_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                after_cursor = page_info.get("endCursor")
            else:
                break
        
        return all_uploads
    
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return None


def fetch_playlist_items(username: str, playlist_slug: str) -> list[dict] | None:
    """
    Fetch all items (cloudcasts) in a playlist via GraphQL API.
    
    Handles pagination automatically to retrieve all items.
    
    Args:
        username: Mixcloud username (owner of the playlist)
        playlist_slug: URL slug for the playlist
    
    Returns:
        List of cloudcast dicts with keys:
        - name: Cloudcast title
        - slug: URL slug for the cloudcast
        
        Returns None if playlist not found or API error.
    """
    all_items = []
    after_cursor = None
    
    try:
        while True:
            resp = requests.post(
                GRAPHQL_URL,
                json={
                    "query": PLAYLIST_ITEMS_QUERY,
                    "variables": {
                        "lookup": {"username": username, "slug": playlist_slug},
                        "first": 50,
                        "after": after_cursor
                    }
                },
                headers={
                    "origin": "https://www.mixcloud.com",
                    "referer": "https://www.mixcloud.com/"
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                print(f"API error: HTTP {resp.status_code}")
                return None
            
            data = resp.json()
            playlist_data = data.get("data", {}).get("playlistLookup")
            
            if playlist_data is None:
                print(f"Playlist not found on Mixcloud: {username}/{playlist_slug}")
                return None
            
            items_data = playlist_data.get("items", {})
            edges = items_data.get("edges", [])
            
            for edge in edges:
                cloudcast = edge.get("node", {}).get("cloudcast")
                if cloudcast is None:
                    continue  # Skip items with null cloudcast (e.g., deleted tracks)
                all_items.append({
                    "name": cloudcast.get("name", "Unknown"),
                    "slug": cloudcast.get("slug", "")
                })
            
            # Check for more pages
            page_info = items_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                after_cursor = page_info.get("endCursor")
            else:
                break
        
        return all_items
    
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return None