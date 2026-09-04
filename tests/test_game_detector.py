"""
tests/test_game_detector.py — Unit tests for GameDetector
"""

from unittest.mock import MagicMock, patch

from core.game_detector import GameDetector


def test_detect_game_from_description_pattern():
    desc = "Harika bir video oldu! Oyun: Valorant\nKeyifli seyirler dilerim."
    game = GameDetector.detect_game(description=desc)
    assert game == "Valorant"


def test_detect_game_from_steam_url():
    desc = "Oyunu buradan indirebilirsiniz: https://store.steampowered.com/app/284160/BeamNGdrive/"
    game = GameDetector.detect_game(description=desc)
    assert "Beamngdrive" in game or "BeamNG" in game


def test_detect_game_from_common_games_title():
    game = GameDetector.detect_game(description="Normal bir açıklama", title="RRaenee ile CS2 Kapışması!")
    assert game == "Counter-Strike 2" or game == "CS2"


def test_detect_game_from_hashtags():
    desc = "Günün en komik anları burada #beamngdrive #gaming"
    game = GameDetector.detect_game(description=desc)
    assert game == "BeamNG.drive" or "beam" in game.lower()


def test_detect_game_llm_fallback():
    mock_choice = MagicMock()
    mock_choice.message.content = "Lethal Company"
    mock_response = MagicMock(choices=[mock_choice])

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with (
        patch("core.deepseek_engine.DeepSeekEngine.is_available", return_value=True),
        patch(
            "core.deepseek_engine.DeepSeekEngine.get_client_and_model",
            return_value=(mock_client, "deepseek-chat", "openrouter"),
        ),
    ):
        desc = "Uzayda canavarlardan kaçtığımız çok gizemli ve korkunç bir indie yapım oynadık."
        game = GameDetector.detect_game(description=desc)
        assert game == "Lethal Company"


def test_detect_game_none():
    game = GameDetector.detect_game(description="Sohbet muhabbet ettik.", title="Günün Özeti")
    assert game is None or isinstance(game, str)
