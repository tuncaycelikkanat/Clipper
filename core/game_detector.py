"""
core/game_detector.py — YouTube Video Açıklamasından ve Meta Verilerinden Oyun Tespiti
"""

from __future__ import annotations

import re
from typing import Optional, List
from loguru import logger


class GameDetector:
    """Detects exact game title primarily from the original YouTube description & metadata."""

    COMMON_GAMES = [
        "BeamNG.drive", "Beam.ng Drive", "BeamNG", "Counter-Strike 2", "CS2", "CS:GO",
        "Valorant", "League of Legends", "LoL", "Grand Theft Auto V", "GTA V", "GTA 5",
        "GTA Online", "Minecraft", "Roblox", "Human Fall Flat", "Lethal Company",
        "PUBG", "PUBG Mobile", "Fortnite", "EA Sports FC 24", "FC 24", "FC 25",
        "FIFA 23", "FIFA", "Apex Legends", "Call of Duty: Warzone", "Warzone",
        "Call of Duty", "Modern Warfare", "Rust", "DayZ", "Rainbow Six Siege", "R6",
        "Overwatch 2", "Rocket League", "Elden Ring", "Cyberpunk 2077", "The Witcher 3",
        "Red Dead Redemption 2", "God of War", "Baldur's Gate 3", "Dota 2",
        "Genshin Impact", "Phasmophobia", "The Forest", "Sons of the Forest",
        "Content Warning", "Chained Together", "Dead by Daylight", "Euro Truck Simulator 2",
        "ETS 2", "Assetto Corsa", "Forza Horizon 5", "Forza", "Rematch",
        "The Stalked", "The Stalked 3", "Supermarket Simulator", "Fears to Fathom",
        "Brawl Stars", "Clash Royale", "Subway Surfers", "Among Us"
    ]

    @classmethod
    def detect_game(
        cls,
        description: str = "",
        title: str = "",
        tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Detects game name using YouTube description first, then title, then tags, then LLM.
        """
        desc_clean = description or ""
        title_clean = title or ""
        combined_text = f"{desc_clean}\n{title_clean}"

        # 1. Açıklama içinde doğrudan 'Oyun:' veya 'Game:' kalıbı arama
        match_game = re.search(
            r"(?:Oyun|Game|Played Game|Oynadığımız Oyun|Oynadığım Oyun)\s*[:\-]\s*([A-Za-z0-9\s:_\-'\+]+?)(?:\n|\r|http|$|\||\.|\/)",
            desc_clean,
            re.IGNORECASE
        )
        if match_game:
            candidate = match_game.group(1).strip()
            if 2 < len(candidate) < 40 and not candidate.lower().startswith("http"):
                logger.info(f"Game detected from description pattern: '{candidate}'")
                return candidate

        # 2. Steam linkinden yakalama
        match_steam = re.search(r"(?:store\.steampowered\.com\/app\/\d+\/)([A-Za-z0-9_]+)", desc_clean, re.IGNORECASE)
        if match_steam:
            steam_name = match_steam.group(1).replace("_", " ").title()
            logger.info(f"Game detected from Steam URL: '{steam_name}'")
            return steam_name

        # 3. Bilinen popüler oyun kütüphanesini açıklama ve başlıkta arama
        for game in cls.COMMON_GAMES:
            escaped = re.escape(game)
            if re.search(r'(?i)(?:\b|_)' + escaped + r'(?:\b|_)', combined_text):
                canonical = "BeamNG.drive" if "beam" in game.lower() else game
                logger.info(f"Game matched from description/title: '{canonical}'")
                return canonical

        # 4. Açıklamadaki hashtag'lerden yakalama
        hashtags = re.findall(r'#([a-zA-Z0-9çğıöşüÇĞİÖŞÜ_]+)', desc_clean)
        for h in hashtags:
            for game in cls.COMMON_GAMES:
                if h.lower() == game.lower().replace(" ", "").replace(".", "").replace(":", ""):
                    return game

        # 5. LLM Fallback (Açıklamadan tek satırda oyun çekme)
        if len(desc_clean) > 30:
            try:
                from core.deepseek_engine import DeepSeekEngine
                if DeepSeekEngine.is_available():
                    client, model_name, _ = DeepSeekEngine.get_client_and_model()
                    prompt = f"Aşağıdaki YouTube video açıklamasında oynanan oyunun adını tek satırda yaz (Örn: 'BeamNG.drive', 'Valorant'). Oyun yoksa 'Bilinmiyor' yaz:\n\n{desc_clean[:500]}"
                    resp = client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                        max_tokens=20
                    )
                    ans = resp.choices[0].message.content.strip().replace("'", "").replace('"', '')
                    if ans and "bilinmiyor" not in ans.lower() and len(ans) < 35:
                        return ans
            except Exception:
                pass

        return None
