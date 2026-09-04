"""
tests/test_metadata_engine.py — Unit tests for YouTubeTagMiner and HumanMetadataEngine
"""

import json
from unittest.mock import MagicMock, patch

from core.metadata_engine import HumanMetadataEngine, YouTubeTagMiner


def test_youtube_tag_miner_get_live_suggestions():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(["query", [["rraenee komik anlar"], ["rraenee beamng"]]]).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = YouTubeTagMiner.get_live_youtube_suggestions("rraenee")
        assert len(res) >= 1
        assert "rraenee komik anlar" in res


def test_youtube_tag_miner_mine_popular_tags():
    with patch.object(
        YouTubeTagMiner, "get_live_youtube_suggestions", return_value=["elraenn komik anlar", "elraenn twitch"]
    ):
        res = YouTubeTagMiner.mine_popular_tags(streamer_name="Elraenn", game_name="Valorant", max_tags=10)
        assert "tags" in res
        assert "hashtags" in res
        assert "tags_comma_separated" in res
        assert any("elraenn" in t.lower() for t in res["tags"])


def test_human_metadata_engine_deepseek():
    mock_result = {
        "titles": {
            "quote_based": "burada ölürsem oyunu silerim dedi ve...",
            "pov_reaction": "kanka 1 canla attığı clutcha bak amk 😂",
            "streamer_tone": "böyle bir şans olamaz ahahaha",
        },
        "recommended_title": "kanka 1 canla attığı clutcha bak amk 😂",
        "hook_caption": "İMKANSIZ CLUTCH!",
        "engagement_question": "Sizce burada suç kimdeydi? Yorumlarda buluşalım 👇",
        "description": "Sizce burada suç kimdeydi? Yorumlarda buluşalım 👇\n\n🎮 Yayıncı: @RRaenee | 🕹️ Oyun: Valorant",
    }

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(mock_result)
    mock_response = MagicMock(choices=[mock_choice])

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with (
        patch("core.deepseek_engine.DeepSeekEngine.is_available", return_value=True),
        patch(
            "core.deepseek_engine.DeepSeekEngine.get_client_and_model",
            return_value=(mock_client, "deepseek-chat", "openrouter"),
        ),
        patch.object(YouTubeTagMiner, "get_live_youtube_suggestions", return_value=["rraenee valorant"]),
    ):
        res = HumanMetadataEngine.generate_metadata(
            transcript_snippet="burada ölürsem oyunu silerim abi arkanda!",
            streamer_name="RRaenee",
            video_title="5v5 Kapışma",
            game_name="Valorant",
        )
        assert res["recommended_title"] == "kanka 1 canla attığı clutcha bak amk 😂"
        assert res["hook_caption"] == "İMKANSIZ CLUTCH!"
        assert "tags" in res
        assert "hashtags" in res


def test_human_metadata_engine_rule_fallback():
    with (
        patch("core.deepseek_engine.DeepSeekEngine.is_available", return_value=False),
        patch("os.getenv", return_value=None),
        patch.object(YouTubeTagMiner, "get_live_youtube_suggestions", return_value=[]),
    ):
        res = HumanMetadataEngine.generate_metadata(
            transcript_snippet="arabayı tamir ettirdim derken kamyon vurdu",
            streamer_name="Hawk Pawk",
            video_title="BeamNG Kamyon",
            game_name="BeamNG.drive",
        )
        assert "titles" in res
        assert "recommended_title" in res
        assert "hook_caption" in res
        assert "description" in res
        assert "tags" in res
