"""
Unit tests for mixcloud_match_to_lrc.py LRC generator.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

from mixcloud_match_to_lrc import process_mp3, walk


def create_mock_audio(tags=None, duration=3600.0):
    """Helper to create a mock mutagen audio file."""
    mock_audio = MagicMock()
    mock_audio.tags = tags
    mock_audio.info.length = duration
    return mock_audio


def create_mock_tags_txxx(url):
    """Create mock tags with TXXX:purl field (most common format)."""
    mock_purl = MagicMock()
    mock_purl.text = [url]
    return {"TXXX:purl": mock_purl}


class TestProcessMp3:
    """Tests for process_mp3 function."""
    
    @patch('mixcloud_match_to_lrc.fetch_tracklist')
    @patch('mixcloud_match_to_lrc.File')
    def test_generates_lrc_file(self, mock_file, mock_fetch, tmp_path):
        """Successfully generates LRC file with track numbers."""
        # Setup mock audio file
        mp3_path = tmp_path / "test-mix.mp3"
        mp3_path.touch()
        
        mock_file.return_value = create_mock_audio(
            tags=create_mock_tags_txxx("https://mixcloud.com/user/test-mix/"),
            duration=600.0
        )
        
        # Setup mock API response
        mock_fetch.return_value = [
            {"__typename": "TrackSection", "startSeconds": 0, "artistName": "Artist 1", "songName": "Song 1"},
            {"__typename": "TrackSection", "startSeconds": 180.5, "artistName": "Artist 2", "songName": "Song 2"},
            {"__typename": "TrackSection", "startSeconds": 360, "artistName": "Artist 3", "songName": "Song 3"},
        ]
        
        process_mp3(mp3_path)
        
        # Verify LRC file created
        lrc_path = tmp_path / "test-mix.lrc"
        assert lrc_path.exists()
        
        # Verify content
        content = lrc_path.read_text()
        assert "[ar:user]" in content
        assert "[ti:test-mix]" in content
        assert "01. Artist 1 – Song 1" in content
        assert "02. Artist 2 – Song 2" in content
        assert "03. Artist 3 – Song 3" in content
    
    @patch('mixcloud_match_to_lrc.fetch_tracklist')
    @patch('mixcloud_match_to_lrc.File')
    def test_track_numbering_format(self, mock_file, mock_fetch, tmp_path):
        """Track numbers are zero-padded (01, 02, etc.)."""
        mp3_path = tmp_path / "mix.mp3"
        mp3_path.touch()
        
        mock_file.return_value = create_mock_audio(
            tags=create_mock_tags_txxx("https://mixcloud.com/user/mix/"),
            duration=600.0
        )
        
        # Create 12 tracks to verify padding
        mock_fetch.return_value = [
            {"__typename": "TrackSection", "startSeconds": i * 50, "artistName": f"Artist {i+1}", "songName": f"Song {i+1}"}
            for i in range(12)
        ]
        
        process_mp3(mp3_path)
        
        content = (tmp_path / "mix.lrc").read_text()
        assert "01. Artist 1" in content
        assert "09. Artist 9" in content
        assert "10. Artist 10" in content
        assert "12. Artist 12" in content
    
    @patch('mixcloud_match_to_lrc.fetch_tracklist')
    @patch('mixcloud_match_to_lrc.File')
    def test_chapter_sections(self, mock_file, mock_fetch, tmp_path):
        """ChapterSection types use chapter field instead of artist/song."""
        mp3_path = tmp_path / "podcast.mp3"
        mp3_path.touch()
        
        mock_file.return_value = create_mock_audio(
            tags=create_mock_tags_txxx("https://mixcloud.com/user/podcast/"),
            duration=3600.0
        )
        
        mock_fetch.return_value = [
            {"__typename": "ChapterSection", "startSeconds": 0, "chapter": "Introduction"},
            {"__typename": "ChapterSection", "startSeconds": 600, "chapter": "Main Topic"},
        ]
        
        process_mp3(mp3_path)
        
        content = (tmp_path / "podcast.lrc").read_text()
        assert "01. Introduction" in content
        assert "02. Main Topic" in content
    
    @patch('mixcloud_match_to_lrc.File')
    def test_skips_file_without_tags(self, mock_file, tmp_path, capsys):
        """Files without tags are skipped."""
        mp3_path = tmp_path / "no-tags.mp3"
        mp3_path.touch()
        
        mock_audio = MagicMock()
        mock_audio.tags = None
        mock_file.return_value = mock_audio
        
        process_mp3(mp3_path)
        
        # No LRC file created
        assert not (tmp_path / "no-tags.lrc").exists()
        
        # Check skip message
        captured = capsys.readouterr()
        assert "Skipping (no tags)" in captured.out
    
    @patch('mixcloud_match_to_lrc.File')
    def test_skips_file_without_mixcloud_url(self, mock_file, tmp_path, capsys):
        """Files without Mixcloud URL in tags are skipped."""
        mp3_path = tmp_path / "no-url.mp3"
        mp3_path.touch()
        
        # Tags exist but no Mixcloud URL
        mock_file.return_value = create_mock_audio(tags={"TIT2": "Some Title"})
        
        process_mp3(mp3_path)
        
        assert not (tmp_path / "no-url.lrc").exists()
        captured = capsys.readouterr()
        assert "Skipping (no podcast URL)" in captured.out
    
    @patch('mixcloud_match_to_lrc.fetch_tracklist')
    @patch('mixcloud_match_to_lrc.File')
    def test_skips_single_section(self, mock_file, mock_fetch, tmp_path, capsys):
        """Files with fewer than 2 sections are skipped."""
        mp3_path = tmp_path / "one-track.mp3"
        mp3_path.touch()
        
        mock_file.return_value = create_mock_audio(
            tags=create_mock_tags_txxx("https://mixcloud.com/user/mix/")
        )
        mock_fetch.return_value = [
            {"__typename": "TrackSection", "startSeconds": 0, "artistName": "Solo", "songName": "Track"}
        ]
        
        process_mp3(mp3_path)
        
        assert not (tmp_path / "one-track.lrc").exists()
        captured = capsys.readouterr()
        assert "Skipping (only 1 section" in captured.out
    
    @patch('mixcloud_match_to_lrc.fetch_tracklist')
    @patch('mixcloud_match_to_lrc.File')
    def test_calculates_timestamps_when_missing(self, mock_file, mock_fetch, tmp_path, capsys):
        """Evenly-spaced timestamps calculated when API lacks timing data."""
        mp3_path = tmp_path / "no-timing.mp3"
        mp3_path.touch()
        
        mock_file.return_value = create_mock_audio(
            tags=create_mock_tags_txxx("https://mixcloud.com/user/mix/"),
            duration=600.0  # 10 minutes
        )
        
        # Sections without startSeconds
        mock_fetch.return_value = [
            {"__typename": "TrackSection", "startSeconds": None, "artistName": "A1", "songName": "S1"},
            {"__typename": "TrackSection", "startSeconds": None, "artistName": "A2", "songName": "S2"},
            {"__typename": "TrackSection", "startSeconds": None, "artistName": "A3", "songName": "S3"},
        ]
        
        process_mp3(mp3_path)
        
        content = (tmp_path / "no-timing.lrc").read_text()
        
        # 3 tracks over 600 seconds = 200 second intervals
        # Track 1 at 0:00, Track 2 at 3:20 (200s), Track 3 at 6:40 (400s)
        assert "[00:00.00]" in content
        assert "[03:20.00]" in content
        assert "[06:40.00]" in content
        
        captured = capsys.readouterr()
        assert "calculating evenly-spaced timestamps" in captured.out
    
    @patch('mixcloud_match_to_lrc.fetch_tracklist')
    @patch('mixcloud_match_to_lrc.File')
    def test_wpub_tag_extraction(self, mock_file, mock_fetch, tmp_path):
        """WPUB tag is used for Mixcloud URL."""
        mp3_path = tmp_path / "wpub.mp3"
        mp3_path.touch()
        
        mock_wpub = MagicMock()
        mock_wpub.url = "https://mixcloud.com/user/wpub-mix/"
        
        mock_file.return_value = create_mock_audio(
            tags={"WPUB": mock_wpub},
            duration=600.0
        )
        
        mock_fetch.return_value = [
            {"__typename": "TrackSection", "startSeconds": 0, "artistName": "A", "songName": "S"},
            {"__typename": "TrackSection", "startSeconds": 300, "artistName": "B", "songName": "T"},
        ]
        
        process_mp3(mp3_path)
        
        assert (tmp_path / "wpub.lrc").exists()
        mock_fetch.assert_called_once_with("user", "wpub-mix")


class TestWalk:
    """Tests for walk directory scanning function."""
    
    @patch('mixcloud_match_to_lrc.process_mp3')
    def test_processes_mp3_files(self, mock_process, tmp_path):
        """Walk finds and processes MP3 files."""
        # Create test MP3 files
        (tmp_path / "file1.mp3").touch()
        (tmp_path / "file2.mp3").touch()
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.mp3").touch()
        
        walk(str(tmp_path))
        
        assert mock_process.call_count == 3
    
    @patch('mixcloud_match_to_lrc.process_mp3')
    def test_ignores_non_mp3_files(self, mock_process, tmp_path):
        """Walk ignores non-MP3 files."""
        (tmp_path / "audio.mp3").touch()
        (tmp_path / "audio.m4a").touch()
        (tmp_path / "audio.wav").touch()
        (tmp_path / "readme.txt").touch()
        
        walk(str(tmp_path))
        
        assert mock_process.call_count == 1
    
    @patch('mixcloud_match_to_lrc.process_mp3')
    def test_continues_on_error(self, mock_process, tmp_path, capsys):
        """Walk continues processing after individual file errors."""
        (tmp_path / "file1.mp3").touch()
        (tmp_path / "file2.mp3").touch()
        (tmp_path / "file3.mp3").touch()
        
        # First file raises error, others succeed
        mock_process.side_effect = [Exception("Test error"), None, None]
        
        walk(str(tmp_path))
        
        # All 3 files attempted
        assert mock_process.call_count == 3
        
        # Error logged
        captured = capsys.readouterr()
        assert "Error on" in captured.out
        assert "Test error" in captured.out
