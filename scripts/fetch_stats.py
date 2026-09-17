"""
scripts/fetch_stats.py — Tek Seferlik YouTube ve Instagram İstatistik Analiz Aracı

Kullanım:
    # 1. YouTube video veya Shorts istatistikleri:
    python scripts/fetch_stats.py --youtube "https://www.youtube.com/shorts/..."
    python scripts/fetch_stats.py --youtube "VIDEO_ID"

    # 2. Instagram Reels / Medya istatistikleri (Graph API ile):
    python scripts/fetch_stats.py --instagram "MEDIA_ID"

    # 3. Bağlı Instagram hesabının son paylaşılan videolarını ve metriklerini listeleme:
    python scripts/fetch_stats.py --instagram-recent

    # 4. İkisini birden tek komutta analiz etme:
    python scripts/fetch_stats.py --youtube "URL" --instagram "MEDIA_ID"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Proje kökünü sys.path'e ekle
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import requests
from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env", override=True)


def extract_youtube_id(url_or_id: str) -> str:
    """URL veya doğrudan ID'den YouTube Video ID'sini ayıklar."""
    url_or_id = url_or_id.strip()
    if len(url_or_id) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id
    patterns = [
        r"(?:v=|\/embed\/|\/shorts\/|youtu\.be\/|\/v\/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id


def get_youtube_stats(url_or_id: str) -> dict:
    """YouTube videosunun güncel izlenme, beğeni, yorum vb. istatistiklerini çeker."""
    video_id = extract_youtube_id(url_or_id)
    print(f"\n[YouTube] Video ID: {video_id} analiz ediliyor...")

    stats = {
        "platform": "YouTube",
        "video_id": video_id,
        "title": None,
        "views": None,
        "likes": None,
        "comments": None,
        "duration_seconds": None,
        "upload_date": None,
        "channel": None,
        "channel_subscribers": None,
        "source": None,
    }

    # 1. Öncelik: yt-dlp ile doğrudan çek (Hızlı, kota harcamaz, herkese açık videolar için kesin çalışır)
    try:
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            if info:
                stats["title"] = info.get("title")
                stats["views"] = info.get("view_count")
                stats["likes"] = info.get("like_count")
                stats["comments"] = info.get("comment_count")
                stats["duration_seconds"] = info.get("duration")
                stats["upload_date"] = info.get("upload_date")
                stats["channel"] = info.get("channel") or info.get("uploader")
                stats["channel_subscribers"] = info.get("channel_follower_count")
                stats["source"] = "yt-dlp (Canlı Metrik)"
                return stats
    except Exception as e:
        print(f"[YouTube] yt-dlp uyarısı: {e}. YouTube Data API deneniyor...")

    # 2. Alternatif: YouTube Data API v3 (token.json veya YOUTUBE_API_KEY varsa)
    try:
        token_path = ROOT_DIR / "token.json"
        if token_path.exists():
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            with open(token_path, "r", encoding="utf-8") as f:
                token_data = json.load(f)
            creds = Credentials.from_authorized_user_info(token_data)
            service = build("youtube", "v3", credentials=creds)
            res = service.videos().list(part="snippet,statistics", id=video_id).execute()
            items = res.get("items", [])
            if items:
                item = items[0]
                snip = item.get("snippet", {})
                st = item.get("statistics", {})
                stats["title"] = snip.get("title")
                stats["views"] = int(st.get("viewCount", 0))
                stats["likes"] = int(st.get("likeCount", 0)) if "likeCount" in st else None
                stats["comments"] = int(st.get("commentCount", 0)) if "commentCount" in st else None
                stats["channel"] = snip.get("channelTitle")
                stats["upload_date"] = snip.get("publishedAt")
                stats["source"] = "YouTube Data API v3 (OAuth2)"
                return stats
    except Exception as e:
        print(f"[YouTube] API hatası: {e}")

    return stats


def get_instagram_stats(media_id: str) -> dict:
    """Instagram Reels / Medya ID'sinin oynatma, beğeni, yorum, erişim verilerini çeker."""
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not access_token:
        return {"error": ".env dosyasında INSTAGRAM_ACCESS_TOKEN bulunamadı."}

    print(f"\n[Instagram] Medya ID: {media_id} analiz ediliyor...")
    base_url = "https://graph.facebook.com/v21.0"

    stats = {
        "platform": "Instagram",
        "media_id": media_id,
        "caption": None,
        "media_type": None,
        "permalink": None,
        "timestamp": None,
        "likes": None,
        "comments": None,
        "insights": {},
    }

    # 1. Temel Medya Alanları (like_count, comments_count, caption vb.)
    try:
        fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
        url = f"{base_url}/{media_id}?fields={fields}&access_token={access_token}"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            stats["caption"] = (data.get("caption") or "")[:120] + "..." if data.get("caption") else None
            stats["media_type"] = data.get("media_product_type") or data.get("media_type")
            stats["permalink"] = data.get("permalink")
            stats["timestamp"] = data.get("timestamp")
            stats["likes"] = data.get("like_count")
            stats["comments"] = data.get("comments_count")
        else:
            err = r.json().get("error", {}).get("message", r.text)
            print(f"[Instagram] Temel veri çekilemedi: {err}")
    except Exception as e:
        print(f"[Instagram] İstek hatası: {e}")

    # 2. Insights (Reels/Video İstatistikleri: plays, reach, saved, shares, total_interactions)
    try:
        metrics = "plays,reach,saved,shares,total_interactions"
        url = f"{base_url}/{media_id}/insights?metric={metrics}&access_token={access_token}"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            insights_data = r.json().get("data", [])
            for item in insights_data:
                name = item.get("name")
                val = item.get("values", [{}])[0].get("value")
                stats["insights"][name] = val
        else:
            # Fotoğraf veya farklı format için alternatif metrikler
            alt_metrics = "impressions,reach,saved"
            url_alt = f"{base_url}/{media_id}/insights?metric={alt_metrics}&access_token={access_token}"
            r_alt = requests.get(url_alt, timeout=15)
            if r_alt.status_code == 200:
                for item in r_alt.json().get("data", []):
                    stats["insights"][item.get("name")] = item.get("values", [{}])[0].get("value")
    except Exception as e:
        print(f"[Instagram] Insights hatası: {e}")

    return stats


def get_instagram_recent_media(limit: int = 5) -> list[dict]:
    """Bağlı Instagram hesabının son paylaşılan videolarını ve metriklerini listeler."""
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    account_id = os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()

    if not access_token or not account_id:
        print("[Instagram] INSTAGRAM_ACCESS_TOKEN veya INSTAGRAM_ACCOUNT_ID eksik!")
        return []

    print(f"\n[Instagram] Hesap ID: {account_id} son {limit} gönderisi taranıyor...")
    base_url = "https://graph.facebook.com/v21.0"
    fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
    url = f"{base_url}/{account_id}/media?fields={fields}&limit={limit}&access_token={access_token}"

    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json().get("data", [])
        else:
            print(f"[Instagram] Hata: {r.json().get('error', {}).get('message', r.text)}")
    except Exception as e:
        print(f"[Instagram] Hata: {e}")
    return []


def format_print_stats(data: dict):
    """Ekrana okunaklı formatta yazdırır."""
    print("=" * 60)
    print(f"  PLATFORM: {data.get('platform')}")
    print("=" * 60)
    for k, v in data.items():
        if k == "insights" and isinstance(v, dict):
            print("  --- Insights / Etkileşim ---")
            for ik, iv in v.items():
                print(f"    • {ik.capitalize()}: {iv}")
        else:
            print(f"  • {k.replace('_', ' ').capitalize()}: {v}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Tek Seferlik YouTube & Instagram İstatistik Analizi")
    parser.add_argument("--youtube", "-y", help="YouTube Video Linki veya Video ID'si")
    parser.add_argument("--instagram", "-i", help="Instagram Medya ID'si (Örn: 18023456789012345)")
    parser.add_argument(
        "--instagram-recent",
        "-ir",
        action="store_true",
        help="Hesabın en son paylaşılan 5 gönderisini ve istatistiklerini getir",
    )
    args = parser.parse_args()

    if not args.youtube and not args.instagram and not args.instagram_recent:
        parser.print_help()
        print("\nÖrnekler:")
        print("  python scripts/fetch_stats.py --youtube 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'")
        print("  python scripts/fetch_stats.py --instagram-recent")
        print("  python scripts/fetch_stats.py --instagram '18023456789012345'")
        return

    if args.youtube:
        yt_res = get_youtube_stats(args.youtube)
        format_print_stats(yt_res)

    if args.instagram:
        ig_res = get_instagram_stats(args.instagram)
        format_print_stats(ig_res)

    if args.instagram_recent:
        items = get_instagram_recent_media(limit=5)
        if items:
            print(f"\n[Instagram] Son {len(items)} Gönderi:")
            for item in items:
                mid = item.get("id")
                print(f"\n--- Medya ID: {mid} ---")
                format_print_stats(get_instagram_stats(mid))


if __name__ == "__main__":
    main()
