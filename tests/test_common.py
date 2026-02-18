"""
Unit tests for mixcloud_common.py shared utilities.
"""

import pytest
from unittest.mock import patch, Mock

from mixcloud_common import extract_lookup, format_lrc_timestamp, fetch_tracklist, fetch_user_playlists


class TestExtractLookup:
    """Tests for extract_lookup URL parsing function."""
    
    def test_valid_url_standard(self):
        """Standard Mixcloud URL extracts username and slug."""
        user, slug = extract_lookup("https://www.mixcloud.com/DJ_Example/cool-mix-2024/")
        assert user == "DJ_Example"
        assert slug == "cool-mix-2024"
    
    def test_valid_url_no_trailing_slash(self):
        """URL without trailing slash works."""
        user, slug = extract_lookup("https://www.mixcloud.com/user/mix-name")
        assert user == "user"
        assert slug == "mix-name"
    
    def test_valid_url_http(self):
        """HTTP (non-HTTPS) URL works."""
        user, slug = extract_lookup("http://mixcloud.com/user/mix")
        assert user == "user"
        assert slug == "mix"
    
    def test_valid_url_no_www(self):
        """URL without www subdomain works."""
        user, slug = extract_lookup("https://mixcloud.com/user/mix/")
        assert user == "user"
        assert slug == "mix"
    
    def test_encoded_url_special_chars(self):
        """URL-encoded characters are decoded (æ, ø, etc.)."""
        # %C3%A6 = æ (ae ligature)
        user, slug = extract_lookup("https://www.mixcloud.com/Glastonauts_Live/fat-tez-%C3%A6lfgifu/")
        assert user == "Glastonauts_Live"
        assert slug == "fat-tez-ælfgifu"
    
    def test_encoded_url_spaces(self):
        """URL-encoded spaces are decoded."""
        user, slug = extract_lookup("https://www.mixcloud.com/user/my%20cool%20mix/")
        assert user == "user"
        assert slug == "my cool mix"
    
    def test_invalid_url_not_mixcloud(self):
        """Non-Mixcloud URL returns (None, None)."""
        user, slug = extract_lookup("https://soundcloud.com/user/mix")
        assert user is None
        assert slug is None
    
    def test_invalid_url_missing_slug(self):
        """URL with only username returns (None, None)."""
        user, slug = extract_lookup("https://mixcloud.com/user/")
        assert user is None
        assert slug is None
    
    def test_invalid_url_empty(self):
        """Empty string returns (None, None)."""
        user, slug = extract_lookup("")
        assert user is None
        assert slug is None
    
    def test_invalid_url_garbage(self):
        """Random garbage returns (None, None)."""
        user, slug = extract_lookup("not a url at all")
        assert user is None
        assert slug is None


class TestFormatLrcTimestamp:
    """Tests for format_lrc_timestamp function."""
    
    def test_zero_seconds(self):
        """Zero seconds formats correctly."""
        assert format_lrc_timestamp(0) == "[00:00.00]"
    
    def test_fractional_seconds(self):
        """Fractional seconds are preserved."""
        assert format_lrc_timestamp(5.5) == "[00:05.50]"
        assert format_lrc_timestamp(5.05) == "[00:05.05]"
    
    def test_one_minute(self):
        """60 seconds = 1 minute."""
        assert format_lrc_timestamp(60) == "[01:00.00]"
    
    def test_minutes_and_seconds(self):
        """Combined minutes and seconds."""
        assert format_lrc_timestamp(65.5) == "[01:05.50]"
        assert format_lrc_timestamp(125.5) == "[02:05.50]"
    
    def test_over_one_hour(self):
        """Times over one hour (no hour field in LRC)."""
        # 61 minutes and 1 second
        assert format_lrc_timestamp(3661.0) == "[61:01.00]"
    
    def test_large_value(self):
        """Very large values (2+ hours)."""
        # 2 hours = 120 minutes
        assert format_lrc_timestamp(7200) == "[120:00.00]"
    
    def test_small_fraction(self):
        """Very small fractions round correctly."""
        assert format_lrc_timestamp(0.01) == "[00:00.01]"
        assert format_lrc_timestamp(0.001) == "[00:00.00]"  # rounds to 0


class TestFetchTracklist:
    """Tests for fetch_tracklist API function."""
    
    @patch('mixcloud_common.requests.post')
    def test_success_with_sections(self, mock_post):
        """Successful API response returns sections list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "cloudcastLookup": {
                    "sections": [
                        {
                            "__typename": "TrackSection",
                            "startSeconds": 0,
                            "artistName": "Artist 1",
                            "songName": "Song 1"
                        },
                        {
                            "__typename": "TrackSection",
                            "startSeconds": 180.5,
                            "artistName": "Artist 2",
                            "songName": "Song 2"
                        }
                    ]
                }
            }
        }
        mock_post.return_value = mock_response
        
        sections = fetch_tracklist("user", "mix-slug")
        
        assert sections is not None
        assert len(sections) == 2
        assert sections[0]["artistName"] == "Artist 1"
        assert sections[1]["startSeconds"] == 180.5
    
    @patch('mixcloud_common.requests.post')
    def test_success_with_chapters(self, mock_post):
        """API response with ChapterSection type."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "cloudcastLookup": {
                    "sections": [
                        {
                            "__typename": "ChapterSection",
                            "startSeconds": 0,
                            "chapter": "Introduction"
                        },
                        {
                            "__typename": "ChapterSection",
                            "startSeconds": 300,
                            "chapter": "Main Content"
                        }
                    ]
                }
            }
        }
        mock_post.return_value = mock_response
        
        sections = fetch_tracklist("user", "podcast-slug")
        
        assert sections is not None
        assert len(sections) == 2
        assert sections[0]["__typename"] == "ChapterSection"
        assert sections[0]["chapter"] == "Introduction"
    
    @patch('mixcloud_common.requests.post')
    def test_cloudcast_not_found(self, mock_post):
        """API returns null cloudcastLookup for non-existent content."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "cloudcastLookup": None
            }
        }
        mock_post.return_value = mock_response
        
        sections = fetch_tracklist("user", "nonexistent-mix")
        
        assert sections is None
    
    @patch('mixcloud_common.requests.post')
    def test_http_error(self, mock_post):
        """Non-200 HTTP status returns None."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        sections = fetch_tracklist("user", "mix")
        
        assert sections is None
    
    @patch('mixcloud_common.requests.post')
    def test_network_error(self, mock_post):
        """Network exception returns None."""
        import requests as req
        mock_post.side_effect = req.RequestException("Connection timeout")
        
        sections = fetch_tracklist("user", "mix")
        
        assert sections is None
    
    @patch('mixcloud_common.requests.post')
    def test_empty_sections(self, mock_post):
        """Cloudcast with no sections returns empty list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "cloudcastLookup": {
                    "sections": []
                }
            }
        }
        mock_post.return_value = mock_response
        
        sections = fetch_tracklist("user", "mix")
        
        assert sections == []
    
    @patch('mixcloud_common.requests.post')
    def test_api_called_with_correct_params(self, mock_post):
        """Verify correct GraphQL query and variables sent."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"cloudcastLookup": {"sections": []}}}
        mock_post.return_value = mock_response
        
        fetch_tracklist("testuser", "testslug")
        
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['json']['variables'] == {
            "lookup": {"username": "testuser", "slug": "testslug"}
        }
        assert "cloudcastLookup" in call_kwargs['json']['query']


class TestFetchUserPlaylists:
    """Tests for fetch_user_playlists function."""
    
    @patch('mixcloud_common.requests.post')
    def test_returns_playlists(self, mock_post):
        """Returns list of playlist dicts with name and slug."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "userLookup": {
                    "playlists": {
                        "edges": [
                            {"node": {"name": "Playlist One", "slug": "playlist-one"}},
                            {"node": {"name": "Playlist Two", "slug": "playlist-two"}}
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None}
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        
        playlists = fetch_user_playlists("testuser")
        
        assert len(playlists) == 2
        assert playlists[0] == {"name": "Playlist One", "slug": "playlist-one"}
        assert playlists[1] == {"name": "Playlist Two", "slug": "playlist-two"}
    
    @patch('mixcloud_common.requests.post')
    def test_handles_pagination(self, mock_post):
        """Fetches multiple pages of playlists."""
        # First page response
        page1 = Mock()
        page1.status_code = 200
        page1.json.return_value = {
            "data": {
                "userLookup": {
                    "playlists": {
                        "edges": [{"node": {"name": "Page 1", "slug": "page-1"}}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor123"}
                    }
                }
            }
        }
        # Second page response
        page2 = Mock()
        page2.status_code = 200
        page2.json.return_value = {
            "data": {
                "userLookup": {
                    "playlists": {
                        "edges": [{"node": {"name": "Page 2", "slug": "page-2"}}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None}
                    }
                }
            }
        }
        mock_post.side_effect = [page1, page2]
        
        playlists = fetch_user_playlists("testuser")
        
        assert len(playlists) == 2
        assert playlists[0]["name"] == "Page 1"
        assert playlists[1]["name"] == "Page 2"
        assert mock_post.call_count == 2
    
    @patch('mixcloud_common.requests.post')
    def test_user_not_found(self, mock_post):
        """Returns None when user doesn't exist."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"userLookup": None}}
        mock_post.return_value = mock_response
        
        result = fetch_user_playlists("nonexistent")
        
        assert result is None
    
    @patch('mixcloud_common.requests.post')
    def test_http_error(self, mock_post):
        """Returns None on HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        result = fetch_user_playlists("testuser")
        
        assert result is None
    
    @patch('mixcloud_common.requests.post')
    def test_network_error(self, mock_post):
        """Returns None on network error."""
        import requests as req
        mock_post.side_effect = req.RequestException("Timeout")
        
        result = fetch_user_playlists("testuser")
        
        assert result is None
    
    @patch('mixcloud_common.requests.post')
    def test_empty_playlists(self, mock_post):
        """Returns empty list when user has no playlists."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "userLookup": {
                    "playlists": {
                        "edges": [],
                        "pageInfo": {"hasNextPage": False}
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        
        playlists = fetch_user_playlists("testuser")
        
        assert playlists == []
    
    @patch('mixcloud_common.requests.post')
    def test_handles_missing_fields(self, mock_post):
        """Handles missing name/slug with defaults."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "userLookup": {
                    "playlists": {
                        "edges": [{"node": {}}],
                        "pageInfo": {"hasNextPage": False}
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        
        playlists = fetch_user_playlists("testuser")
        
        assert playlists[0] == {"name": "Unknown", "slug": ""}