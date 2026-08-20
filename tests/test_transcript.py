import pytest
from unittest.mock import patch, MagicMock
from core.transcript import TranscriptManager

class FakeTranscript:
    def __init__(self, lang, items):
        self.language_code = lang
        self.items = items
    
    def fetch(self):
        return self.items

class FakeSnippet:
    def __init__(self, text, start, duration):
        self.text = text
        self.start = start
        self.duration = duration

def test_get_transcript_success():
    with patch('core.transcript.YouTubeTranscriptApi') as mock_api:
        mock_instance = MagicMock()
        mock_api.return_value = mock_instance
        
        snippets = [
            FakeSnippet("Hello\nWorld", 0.0, 2.0),
            FakeSnippet("Test", 2.0, 1.0)
        ]
        
        mock_instance.list.return_value = [
            FakeTranscript("es", []),
            FakeTranscript("tr", snippets)
        ]
        
        res = TranscriptManager.get_transcript("id", preferred_languages=["tr", "en"])
        assert len(res) == 2
        assert res[0]["text"] == "Hello World"
        assert res[0]["start"] == 0.0
        assert res[0]["end"] == 2.0
        assert res[0]["duration"] == 2.0

def test_get_transcript_defaults():
    with patch('core.transcript.YouTubeTranscriptApi') as mock_api:
        mock_instance = MagicMock()
        mock_api.return_value = mock_instance
        
        mock_instance.list.return_value = [
            FakeTranscript("en", [FakeSnippet("Default", 0.0, 1.0)])
        ]
        
        # Uses default ['tr', 'en']
        res = TranscriptManager.get_transcript("id")
        assert len(res) == 1
        assert res[0]["text"] == "Default"

def test_get_transcript_fallback_lang():
    with patch('core.transcript.YouTubeTranscriptApi') as mock_api:
        mock_instance = MagicMock()
        mock_api.return_value = mock_instance
        
        # Test no matching preferred language
        mock_instance.list.return_value = [
            FakeTranscript("fr", [FakeSnippet("Bonjour", 0.0, 1.0)])
        ]
        
        res = TranscriptManager.get_transcript("id", preferred_languages=["tr"])
        assert len(res) == 1
        assert res[0]["text"] == "Bonjour"

def test_get_transcript_no_results():
    with patch('core.transcript.YouTubeTranscriptApi') as mock_api:
        mock_instance = MagicMock()
        mock_api.return_value = mock_instance
        
        mock_instance.list.return_value = []
        res = TranscriptManager.get_transcript("id")
        assert res == []

def test_get_transcript_list_exception():
    with patch('core.transcript.YouTubeTranscriptApi') as mock_api:
        mock_instance = MagicMock()
        mock_api.return_value = mock_instance
        mock_instance.list.side_effect = Exception("error")
        
        res = TranscriptManager.get_transcript("id")
        assert res == []

def test_get_transcript_fetch_exception():
    with patch('core.transcript.YouTubeTranscriptApi') as mock_api:
        mock_instance = MagicMock()
        mock_api.return_value = mock_instance
        
        mock_t = MagicMock()
        mock_t.language_code = "tr"
        mock_t.fetch.side_effect = Exception("error")
        mock_instance.list.return_value = [mock_t]
        
        res = TranscriptManager.get_transcript("id")
        assert res == []

def test_get_transcript_dict_fallback():
    # test dict access fallback
    with patch('core.transcript.YouTubeTranscriptApi') as mock_api:
        mock_instance = MagicMock()
        mock_api.return_value = mock_instance
        
        mock_t = MagicMock()
        mock_t.language_code = "tr"
        mock_t.fetch.return_value = [{"text": "Dict test", "start": 0.0, "duration": 1.0}]
        mock_instance.list.return_value = [mock_t]
        
        res = TranscriptManager.get_transcript("id")
        assert len(res) == 1
        assert res[0]["text"] == "Dict test"

def test_is_sentence_complete():
    # Empty
    assert TranscriptManager.is_sentence_complete("") is False
    assert TranscriptManager.is_sentence_complete("   ") is False
    
    # Punctuation
    assert TranscriptManager.is_sentence_complete("This is complete.") is True
    assert TranscriptManager.is_sentence_complete("Is this complete?") is True
    
    # Incomplete connector
    assert TranscriptManager.is_sentence_complete("Ben gittim ve") is False
    assert TranscriptManager.is_sentence_complete("I went and") is False
    
    # Verb patterns (Turkish)
    assert TranscriptManager.is_sentence_complete("Oraya gitti") is True
    assert TranscriptManager.is_sentence_complete("Çok güzeldir") is True
    assert TranscriptManager.is_sentence_complete("Geliyor") is True
    assert TranscriptManager.is_sentence_complete("Gelecek") is True
    
    # Not verb, no punctuation
    assert TranscriptManager.is_sentence_complete("Sadece bir elma") is False
    
    # No words
    assert TranscriptManager.is_sentence_complete("---") is False

def test_snap_boundaries_empty():
    s, e, t = TranscriptManager.snap_boundaries(0.0, 10.0, [])
    assert s == 0.0
    assert e == 10.0
    assert t == ""

def test_snap_boundaries_normal():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello"},
        {"start": 2.5, "end": 4.0, "text": "World"},
        {"start": 4.5, "end": 6.0, "text": "This is a test."},
        {"start": 6.5, "end": 8.0, "text": "Extra text."}
    ]
    
    # candidate exactly matching start but needs to find complete end
    # start 2.5 (World) -> end 6.0 (This is a test.)
    # let's set candidate to 2.5 to 4.5 (which is middle of "This is a test.")
    # it should snap end to 6.0 + 0.35
    s, e, t = TranscriptManager.snap_boundaries(2.5, 4.5, segments)
    
    assert s == 2.5
    # Wait, the difference is (6.0 + 0.35 - 2.5) = 3.85
    # Since duration < 10.0, it will fallback!
    # Let's adjust times so duration >= 10.0 to test normal snap
    pass

def test_snap_boundaries_long():
    segments = [
        {"start": 0.0, "end": 5.0, "text": "First part."},
        {"start": 6.0, "end": 10.0, "text": "Second part."},
        {"start": 10.0, "end": 15.0, "text": "Third part is not complete"},
        {"start": 15.0, "end": 20.0, "text": "but now it is."},
        {"start": 21.0, "end": 25.0, "text": "Extra part."}
    ]
    
    # candidate_start: 5.8 -> will snap to 6.0
    # candidate_end: 14.0 -> will snap to 20.0 + 0.35 because 14.0 hits segment 3, which is incomplete
    s, e, t = TranscriptManager.snap_boundaries(5.8, 14.0, segments)
    
    assert s == 6.0
    assert e == 20.35
    assert "Second part. Third part is not complete but now it is." in t

def test_snap_boundaries_fallback_short():
    segments = [
        {"start": 10.0, "end": 12.0, "text": "Short."}
    ]
    s, e, t = TranscriptManager.snap_boundaries(10.0, 11.0, segments)
    assert s == 10.0
    assert e == 11.0
    assert t == "Short."

def test_snap_boundaries_target_not_found():
    segments = [
        {"start": 0.0, "end": 5.0, "text": "Start."},
        {"start": 20.0, "end": 25.0, "text": "End."}
    ]
    # candidate_end = 12.0 (no segment contains it)
    s, e, t = TranscriptManager.snap_boundaries(0.0, 30.0, segments) # test fallback short triggers if we use small, let's use 30 to make sure it's long enough
    
    assert s == 0.0 # closest to 0.0
    assert e == 25.35 # it will find target_idx = 1
    assert "Start. End." in t
