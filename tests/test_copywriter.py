"""
tests/test_copywriter.py — Tests for CopywriterEngine
"""

from unittest.mock import MagicMock

from core.copywriter import CopywriterEngine


def test_copywriter_deepseek_success():
    mock_ds = MagicMock()
    mock_ds.generate_shorts_copy.return_value = {
        "title": "Efsane An #Shorts",
        "description": "Açıklama metni",
        "tags": ["gaming", "shorts"],
    }
    engine = CopywriterEngine(deepseek=mock_ds)
    res = engine.generate_shorts_metadata(
        clip={"title": "Vuruş", "hook_caption": "Bunu izle", "category": "CLUTCH"},
        video_title="CS2 Maçı",
        channel_name="ProGamer",
    )
    assert res["title"] == "Efsane An #Shorts"
    assert "Açıklama" in res["description"]


def test_copywriter_deepseek_failure_fallback():
    mock_ds = MagicMock()
    mock_ds.generate_shorts_copy.side_effect = Exception("API error")
    engine = CopywriterEngine(deepseek=mock_ds)

    res = engine.generate_shorts_metadata(
        clip={"title": "Çok Uzun Başlık " * 10, "hook_caption": "İnanılmaz", "category": "FUNNY"},
        video_title="PUBG Yayını",
        channel_name="Mithrain",
    )
    assert "#Shorts" in res["title"]
    assert "PUBG Yayını" in res["description"]
    assert "Mithrain" in res["description"]
    assert "funny" in res["tags"]
