#!/usr/bin/env python3
"""scripts/benchmark_video.py — Measure exact execution time per pipeline step."""
import sys
import os
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.pipeline import ClipperPipeline
from core.logger import logger

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/gMmUpWErSEo?si=yV-19Y8AZFF6QmXv"
    target_clips = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    print(f"🎬 Benchmark Başlatılıyor: {url}")
    print(f"🎯 Hedef Klip Sayısı: {target_clips}\n")

    pipeline = ClipperPipeline(output_dir="outputs/clips")

    def progress_printer(msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    start_t = time.perf_counter()
    results = pipeline.execute(
        url=url,
        target_clips=target_clips,
        render_mode="shorts_9x16_black",
        add_subtitles=True,
        add_hook_card=True,
        enhance_colors=True,
        progress_callback=progress_printer,
    )
    total_t = time.perf_counter() - start_t

    print("\n" + "=" * 60)
    print(f"✅ Benchmark Tamamlandı! Toplam Süre: {total_t:.2f}s ({total_t/60:.2f} dk)")
    print(f"🎥 Üretilen Klip Sayısı: {len(results)}")
    for r in results:
        print(f"  - [{r.get('clip_id')}] {r.get('title')} ({r.get('duration')}s) -> {r.get('render_path')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
