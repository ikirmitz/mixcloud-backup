"""
Unit tests for mixcloud_downloader.py automated downloader.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

from mixcloud_downloader import (
    get_user_playlists,
    get_playlist_entries,
    detect_audio_codec,
    extract_codec_from_info,
    fetch_track_info,
    _extract_entries,
)


class TestExtractEntries:
    """Tests for _extract_entries helper function."""
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_extracts_entries(self, mock_ytdl_class):
        """Returns list of entries from yt-dlp extraction."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'entries': [
                {'url': 'https://mixcloud.com/user/mix1/', 'title': 'Mix 1'},
                {'url': 'https://mixcloud.com/user/mix2/', 'title': 'Mix 2'},
            ]
        }
        mock_ytdl_class.return_value = mock_ydl
        
        entries = _extract_entries("https://mixcloud.com/user/playlists/")
        
        assert len(entries) == 2
        assert entries[0]['title'] == 'Mix 1'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_filters_none_entries(self, mock_ytdl_class):
        """None entries in the list are filtered out."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'entries': [
                {'url': 'https://mixcloud.com/user/mix1/', 'title': 'Mix 1'},
                None,
                {'url': 'https://mixcloud.com/user/mix2/', 'title': 'Mix 2'},
                None,
            ]
        }
        mock_ytdl_class.return_value = mock_ydl
        
        entries = _extract_entries("https://mixcloud.com/user/playlists/")
        
        assert len(entries) == 2
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_returns_empty_on_no_entries(self, mock_ytdl_class):
        """Returns empty list when no entries key."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {'id': 'something'}
        mock_ytdl_class.return_value = mock_ydl
        
        entries = _extract_entries("https://mixcloud.com/user/mix/")
        
        assert entries == []


class TestGetUserPlaylists:
    """Tests for get_user_playlists function."""
    
    @patch('mixcloud_downloader.fetch_user_playlists')
    def test_returns_playlists(self, mock_fetch):
        """Returns formatted playlist dicts with url and title."""
        mock_fetch.return_value = [
            {'name': 'My Playlist', 'slug': 'playlist1'},
            {'name': 'Another Playlist', 'slug': 'playlist2'},
        ]
        
        playlists = get_user_playlists("testuser")
        
        assert len(playlists) == 2
        assert playlists[0] == {'url': 'https://www.mixcloud.com/testuser/playlists/playlist1/', 'title': 'My Playlist'}
        assert playlists[1] == {'url': 'https://www.mixcloud.com/testuser/playlists/playlist2/', 'title': 'Another Playlist'}
        mock_fetch.assert_called_once_with("testuser")
    
    @patch('mixcloud_downloader.fetch_user_playlists')
    def test_returns_empty_on_none(self, mock_fetch):
        """Returns empty list when API returns None."""
        mock_fetch.return_value = None
        
        playlists = get_user_playlists("testuser")
        
        assert playlists == []
    
    @patch('mixcloud_downloader.fetch_user_playlists')
    def test_returns_empty_list(self, mock_fetch):
        """Returns empty list when user has no playlists."""
        mock_fetch.return_value = []
        
        playlists = get_user_playlists("testuser")
        
        assert playlists == []


class TestGetPlaylistEntries:
    """Tests for get_playlist_entries function."""
    
    @patch('mixcloud_downloader._extract_entries')
    def test_returns_entries_with_urls(self, mock_extract):
        """Returns only entries that have URLs."""
        mock_extract.return_value = [
            {'url': 'https://mixcloud.com/user/mix1/', 'title': 'Mix 1'},
            {'title': 'Mix No URL'},  # Missing URL
            {'url': 'https://mixcloud.com/user/mix2/', 'title': 'Mix 2'},
        ]
        
        entries = get_playlist_entries("https://mixcloud.com/user/playlist/")
        
        assert len(entries) == 2
        assert all(e.get('url') for e in entries)
    
    @patch('mixcloud_downloader._extract_entries')
    def test_returns_empty_on_error(self, mock_extract):
        """Returns empty list on extraction error."""
        mock_extract.side_effect = Exception("Network error")
        
        entries = get_playlist_entries("https://mixcloud.com/user/playlist/")
        
        assert entries == []


class TestDetectAudioCodec:
    """Tests for detect_audio_codec function."""
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_detects_opus(self, mock_ytdl_class):
        """Detects opus codec from formats."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'formats': [
                {'format_id': 'http', 'acodec': 'opus', 'ext': 'webm'},
            ]
        }
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'opus'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_detects_aac(self, mock_ytdl_class):
        """Detects aac codec from formats."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'formats': [
                {'format_id': 'http', 'acodec': 'aac', 'ext': 'm4a'},
            ]
        }
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'aac'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_detects_mp4a_as_aac(self, mock_ytdl_class):
        """Detects mp4a codec as aac."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'formats': [
                {'format_id': 'http', 'acodec': 'mp4a.40.2', 'ext': 'm4a'},
            ]
        }
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'aac'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_uses_top_level_acodec_fallback(self, mock_ytdl_class):
        """Falls back to top-level acodec when formats empty."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'formats': [],
            'acodec': 'opus'
        }
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'opus'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_returns_unknown_on_no_codec(self, mock_ytdl_class):
        """Returns 'unknown' when no codec can be determined."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'formats': [
                {'format_id': 'http', 'acodec': 'none'},
            ]
        }
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'unknown'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_returns_unknown_on_error(self, mock_ytdl_class):
        """Returns 'unknown' when extraction fails."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.side_effect = Exception("Network error")
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'unknown'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_skips_video_only_formats(self, mock_ytdl_class):
        """Skips formats where acodec is 'none' (video only)."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'formats': [
                {'format_id': 'video', 'acodec': 'none', 'vcodec': 'h264'},
                {'format_id': 'audio', 'acodec': 'opus', 'vcodec': 'none'},
            ]
        }
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'opus'
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_handles_none_formats(self, mock_ytdl_class):
        """Handles None formats list gracefully."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {
            'formats': None,
            'acodec': 'aac'
        }
        mock_ytdl_class.return_value = mock_ydl
        
        codec = detect_audio_codec("https://mixcloud.com/user/mix/")
        
        assert codec == 'aac'


class TestExtractCodecFromInfo:
    """Tests for extract_codec_from_info pure function."""
    
    def test_returns_unknown_for_none(self):
        """Returns 'unknown' when info is None."""
        assert extract_codec_from_info(None) == 'unknown'
    
    def test_returns_unknown_for_empty_dict(self):
        """Returns 'unknown' for empty info dict."""
        assert extract_codec_from_info({}) == 'unknown'
    
    def test_detects_opus_from_formats(self):
        """Detects opus codec from formats list."""
        info = {'formats': [{'acodec': 'opus', 'ext': 'webm'}]}
        assert extract_codec_from_info(info) == 'opus'
    
    def test_detects_aac_from_formats(self):
        """Detects aac codec from formats list."""
        info = {'formats': [{'acodec': 'aac', 'ext': 'm4a'}]}
        assert extract_codec_from_info(info) == 'aac'
    
    def test_detects_mp4a_as_aac(self):
        """Detects mp4a.40.2 as aac."""
        info = {'formats': [{'acodec': 'mp4a.40.2'}]}
        assert extract_codec_from_info(info) == 'aac'
    
    def test_skips_none_acodec(self):
        """Skips formats with acodec='none' (video only)."""
        info = {
            'formats': [
                {'acodec': 'none', 'vcodec': 'h264'},
                {'acodec': 'opus'},
            ]
        }
        assert extract_codec_from_info(info) == 'opus'
    
    def test_falls_back_to_top_level_acodec(self):
        """Falls back to top-level acodec when formats empty."""
        info = {'formats': [], 'acodec': 'opus'}
        assert extract_codec_from_info(info) == 'opus'
    
    def test_handles_none_formats_list(self):
        """Handles None formats list gracefully."""
        info = {'formats': None, 'acodec': 'aac'}
        assert extract_codec_from_info(info) == 'aac'
    
    def test_case_insensitive_codec_detection(self):
        """Codec detection is case-insensitive."""
        info = {'formats': [{'acodec': 'OPUS'}]}
        assert extract_codec_from_info(info) == 'opus'


class TestFetchTrackInfo:
    """Tests for fetch_track_info function."""
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_returns_info_dict(self, mock_ytdl_class):
        """Returns info dict on success."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.return_value = {'title': 'Test Mix', 'uploader': 'DJ'}
        mock_ytdl_class.return_value = mock_ydl
        
        info = fetch_track_info("https://mixcloud.com/user/mix/")
        
        assert info == {'title': 'Test Mix', 'uploader': 'DJ'}
    
    @patch('mixcloud_downloader.yt_dlp.YoutubeDL')
    def test_returns_none_on_error(self, mock_ytdl_class):
        """Returns None on extraction error."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = Mock(return_value=mock_ydl)
        mock_ydl.__exit__ = Mock(return_value=False)
        mock_ydl.extract_info.side_effect = Exception("Track not found")
        mock_ytdl_class.return_value = mock_ydl
        
        info = fetch_track_info("https://mixcloud.com/user/missing/")
        
        assert info is None