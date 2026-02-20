"""
Unit tests for mixcloud_match_to_lrc.py LRC generator.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

from mixcloud_match_to_lrc import (
    process_mp3,
    walk,
    generate_lrc_content,
    embed_lyrics,
    embed_lyrics_any,
    extract_mixcloud_url,
    process_audio_from_tags,
)


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
        """Successfully generates LRC file when write_file=True."""
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
        
        process_mp3(mp3_path, embed=False, write_file=True)
        
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
        
        process_mp3(mp3_path, embed=False, write_file=True)
        
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
        
        process_mp3(mp3_path, embed=False, write_file=True)
        
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
        assert "Skipping (no tags in file)" in captured.out
    
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
        assert "Skipping (no Mixcloud URL in tags)" in captured.out
    
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
        
        process_mp3(mp3_path, embed=False, write_file=True)
        
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
        
        process_mp3(mp3_path, embed=False, write_file=True)
        
        assert (tmp_path / "wpub.lrc").exists()
        mock_fetch.assert_called_once_with("user", "wpub-mix")


class TestWalk:
    """Tests for walk directory scanning function."""
    
    @patch('mixcloud_match_to_lrc.process_audio_from_tags')
    def test_processes_supported_audio_files(self, mock_process, tmp_path):
        """Walk finds and processes supported audio files."""
        (tmp_path / "file1.mp3").touch()
        (tmp_path / "file2.m4a").touch()
        (tmp_path / "file3.opus").touch()
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file4.ogg").touch()
        
        walk(str(tmp_path))
        
        assert mock_process.call_count == 4
    
    @patch('mixcloud_match_to_lrc.process_audio_from_tags')
    def test_ignores_unsupported_files(self, mock_process, tmp_path):
        """Walk ignores unsupported file extensions."""
        (tmp_path / "audio.mp3").touch()
        (tmp_path / "audio.wav").touch()
        (tmp_path / "readme.txt").touch()
        
        walk(str(tmp_path))
        
        assert mock_process.call_count == 1
    
    @patch('mixcloud_match_to_lrc.process_audio_from_tags')
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


class TestGenerateLrcContent:
    """Tests for generate_lrc_content function."""
    
    def test_basic_track_sections(self):
        """Generate LRC from track sections."""
        sections = [
            {"__typename": "TrackSection", "startSeconds": 0, "artistName": "Artist One", "songName": "Song One"},
            {"__typename": "TrackSection", "startSeconds": 180.5, "artistName": "Artist Two", "songName": "Song Two"},
        ]
        
        content = generate_lrc_content("testuser", "Test Mix", sections)
        
        assert "[ar:testuser]" in content
        assert "[ti:Test Mix]" in content
        assert "[00:00.00] 01. Artist One – Song One" in content
        assert "[03:00.50] 02. Artist Two – Song Two" in content
    
    def test_chapter_sections(self):
        """Generate LRC from chapter sections."""
        sections = [
            {"__typename": "ChapterSection", "startSeconds": 0, "chapter": "Introduction"},
            {"__typename": "ChapterSection", "startSeconds": 300, "chapter": "Main Set"},
        ]
        
        content = generate_lrc_content("dj", "Podcast", sections)
        
        assert "[00:00.00] 01. Introduction" in content
        assert "[05:00.00] 02. Main Set" in content
    
    def test_mixed_sections(self):
        """Generate LRC from mixed section types."""
        sections = [
            {"__typename": "ChapterSection", "startSeconds": 0, "chapter": "Intro"},
            {"__typename": "TrackSection", "startSeconds": 60, "artistName": "Artist", "songName": "Track"},
        ]
        
        content = generate_lrc_content("user", "Mix", sections)
        
        assert "[00:00.00] 01. Intro" in content
        assert "[01:00.00] 02. Artist – Track" in content
    
    def test_header_format(self):
        """LRC header includes artist and title tags."""
        sections = [
            {"__typename": "TrackSection", "startSeconds": 0, "artistName": "A", "songName": "B"},
            {"__typename": "TrackSection", "startSeconds": 60, "artistName": "C", "songName": "D"},
        ]
        
        content = generate_lrc_content("myuser", "My Mix Title", sections)
        
        lines = content.split('\n')
        assert lines[0] == "[ar:myuser]"
        assert lines[1] == "[ti:My Mix Title]"
        assert lines[2] == ""  # Blank line after header


class TestEmbedLyrics:
    """Tests for embed_lyrics function."""
    
    @patch('mixcloud_match_to_lrc.ID3')
    def test_embed_success(self, mock_id3_class):
        """Successfully embed lyrics."""
        mock_audio = MagicMock()
        mock_id3_class.return_value = mock_audio
        
        result = embed_lyrics(Path("/test/file.mp3"), "[ar:test]\nLyrics content")
        
        assert result is True
        mock_audio.delall.assert_called_once_with('USLT')
        mock_audio.add.assert_called_once()
        mock_audio.save.assert_called_once()
    
    @patch('mixcloud_match_to_lrc.ID3')
    def test_embed_removes_existing_uslt(self, mock_id3_class):
        """Existing USLT tags are removed before adding new one."""
        mock_audio = MagicMock()
        mock_id3_class.return_value = mock_audio
        
        embed_lyrics(Path("/test/file.mp3"), "content")
        
        # Verify delall called before add
        mock_audio.delall.assert_called_once_with('USLT')
        mock_audio.add.assert_called_once()
    
    @patch('mixcloud_match_to_lrc.ID3')
    def test_embed_failure_returns_false(self, mock_id3_class):
        """Returns False on save error."""
        mock_audio = MagicMock()
        mock_audio.save.side_effect = Exception("Write error")
        mock_id3_class.return_value = mock_audio
        
        result = embed_lyrics(Path("/test/file.mp3"), "content")
        
        assert result is False
    
    @patch('mixcloud_match_to_lrc.ID3')
    def test_embed_creates_new_id3_on_load_error(self, mock_id3_class):
        """Creates new ID3 object if file has no tags."""
        # First call raises (loading existing), second returns new mock
        mock_audio = MagicMock()
        mock_id3_class.side_effect = [Exception("No ID3 header"), mock_audio]
        
        result = embed_lyrics(Path("/test/file.mp3"), "content")
        
        # Should have tried twice: first load, then create new
        assert mock_id3_class.call_count == 2
        assert result is True


class TestEmbedLyricsAny:
    """Tests for embed_lyrics_any multi-format embedding."""
    
    @patch('mixcloud_match_to_lrc.MP4')
    def test_embeds_mp4_lyrics(self, mock_mp4_class, tmp_path):
        """Writes MP4 lyrics to ©lyr tag."""
        audio_path = tmp_path / "test.m4a"
        audio_path.touch()
        
        mock_audio = MagicMock()
        mock_audio.tags = {}
        mock_mp4_class.return_value = mock_audio
        
        result = embed_lyrics_any(audio_path, "lrc content")
        
        assert result is True
        assert "\xa9lyr" in mock_audio.tags
        mock_audio.save.assert_called_once()
    
    @patch('mixcloud_match_to_lrc.OggOpus')
    def test_embeds_ogg_opus_lyrics(self, mock_ogg_opus_class, tmp_path):
        """Writes Ogg Opus lyrics to vorbis comment."""
        audio_path = tmp_path / "test.opus"
        audio_path.touch()
        
        mock_audio = MagicMock()
        mock_audio.tags = {}
        mock_ogg_opus_class.return_value = mock_audio
        
        result = embed_lyrics_any(audio_path, "lrc content")
        
        assert result is True
        assert "lyrics" in mock_audio.tags
        mock_audio.save.assert_called_once()
    
    @patch('mixcloud_match_to_lrc.OggVorbis')
    @patch('mixcloud_match_to_lrc.OggOpus')
    def test_falls_back_to_ogg_vorbis(self, mock_ogg_opus_class, mock_ogg_vorbis_class, tmp_path):
        """Falls back to Ogg Vorbis when Ogg Opus fails."""
        audio_path = tmp_path / "test.ogg"
        audio_path.touch()
        
        mock_ogg_opus_class.side_effect = Exception("Not Opus")
        mock_audio = MagicMock()
        mock_audio.tags = {}
        mock_ogg_vorbis_class.return_value = mock_audio
        
        result = embed_lyrics_any(audio_path, "lrc content")
        
        assert result is True
        assert "lyrics" in mock_audio.tags
        mock_audio.save.assert_called_once()
    
    def test_returns_false_for_unsupported(self, tmp_path):
        """Returns False for unsupported formats."""
        audio_path = tmp_path / "test.wav"
        audio_path.touch()
        
        result = embed_lyrics_any(audio_path, "lrc content")
        
        assert result is False


class TestExtractMixcloudUrl:
    """Tests for extract_mixcloud_url helper."""
    
    def test_extracts_from_txxx_purl(self):
        mock_purl = MagicMock()
        mock_purl.text = ["https://mixcloud.com/user/mix/"]
        tags = {"TXXX:purl": mock_purl}
        
        assert extract_mixcloud_url(tags) == "https://mixcloud.com/user/mix/"
    
    def test_extracts_from_wxxx_case_insensitive(self):
        mock_wxxx = MagicMock()
        mock_wxxx.url = "https://mixcloud.com/user/wxxx/"
        tags = {"wXxX:pUrL": mock_wxxx}
        
        assert extract_mixcloud_url(tags) == "https://mixcloud.com/user/wxxx/"
    
    def test_extracts_from_purl_or_url(self):
        tags = {"purl": ["https://mixcloud.com/user/purl/"]}
        assert extract_mixcloud_url(tags) == "https://mixcloud.com/user/purl/"
        
        tags = {"url": ["https://mixcloud.com/user/url/"]}
        assert extract_mixcloud_url(tags) == "https://mixcloud.com/user/url/"
    
    def test_extracts_from_comment(self):
        tags = {"comment": ["see https://mixcloud.com/user/comment/"]}
        assert extract_mixcloud_url(tags) == "see https://mixcloud.com/user/comment/"
    
    def test_returns_none_without_mixcloud(self):
        tags = {"comment": ["not a match"]}
        assert extract_mixcloud_url(tags) is None


class TestProcessAudioFromTags:
    """Tests for process_audio_from_tags wrapper."""
    
    @patch('mixcloud_match_to_lrc.process_audio_with_url')
    @patch('mixcloud_match_to_lrc.File')
    def test_processes_when_url_present(self, mock_file, mock_process, tmp_path):
        audio_path = tmp_path / "test.m4a"
        audio_path.touch()
        
        tags = {"purl": ["https://mixcloud.com/user/mix/"]}
        mock_file.return_value = create_mock_audio(tags=tags)
        
        process_audio_from_tags(audio_path, embed=True, write_file=False)
        
        mock_process.assert_called_once_with(audio_path, "https://mixcloud.com/user/mix/", embed=True, write_file=False)
    
    @patch('mixcloud_match_to_lrc.File')
    def test_skips_when_no_tags(self, mock_file, tmp_path, capsys):
        audio_path = tmp_path / "test.m4a"
        audio_path.touch()
        
        mock_audio = MagicMock()
        mock_audio.tags = None
        mock_file.return_value = mock_audio
        
        process_audio_from_tags(audio_path, embed=True, write_file=False)
        
        captured = capsys.readouterr()
        assert "Skipping (no tags in file)" in captured.out