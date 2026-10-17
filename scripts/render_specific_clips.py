import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.cutter import VideoCutter
from core.database import DatabaseManager
from core.thumbnail import ThumbnailGenerator
from loguru import logger

def main():
    db = DatabaseManager()
    db.init_db()

    video_path = os.path.abspath("downloads/GKG5MoGq6Bg.webm")
    if not os.path.exists(video_path):
        logger.error(f"Source video not found at {video_path}")
        return

    cutter = VideoCutter(output_dir="outputs/clips")
    thumb_dir = os.path.abspath("outputs/thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)

    target_clips = [
        {
            "id": "GKG5MoGq6Bg_clip_1",
            "title": "kanka gece 3'te oynanan modun gerginlık seviyesi 😂",
            "start_time": 61.84,
            "end_time": 109.79,
            "hook_caption": "ŞEYTANİ SESLER ÇIKARIYOR!",
        },
        {
            "id": "GKG5MoGq6Bg_clip_2",
            "title": "oha bir sürü sandığın olduğu yere geldim ama...",
            "start_time": 844.32,
            "end_time": 879.63,
            "hook_caption": "OHA BU NE?!",
        },
        {
            "id": "GKG5MoGq6Bg_clip_4",
            "title": "zırhlar gitti abi oha oha oha",
            "start_time": 913.68,
            "end_time": 954.79,
            "hook_caption": "ZIRHLAR GİTTİ!",
        },
        {
            "id": "GKG5MoGq6Bg_clip_7",
            "title": "bu adamın ne yapacağını algılayamıyorum ya",
            "start_time": 244.44,
            "end_time": 286.91,
            "hook_caption": "BU NE OĞLUM?!",
        },
    ]

    for item in target_clips:
        cid = item["id"]
        logger.info(f"==> Rendering clip: {cid} ({item['title']}) [{item['start_time']}s - {item['end_time']}s]")
        t0 = time.time()
        try:
            render_path = cutter.cut_clip(
                url=video_path,
                start_time=item["start_time"],
                end_time=item["end_time"],
                clip_id=cid,
                video_title="",
                hook_caption=item["hook_caption"],
                render_mode="shorts_9x16_blur",
                add_subtitles=False,
                add_hook_card=False,
                enhance_colors=True,
                use_whisper=False,
            )
            render_path = os.path.abspath(render_path)
            logger.info(f"Rendered to: {render_path} (took {time.time() - t0:.1f}s)")

            # Extract thumbnail
            cand_thumb = os.path.join(thumb_dir, f"thumb_{cid}.jpg")
            try:
                ThumbnailGenerator.extract_best_frame(
                    video_path=render_path,
                    peak_time=1.0,
                    output_path=cand_thumb,
                )
                logger.info(f"Thumbnail extracted: {cand_thumb}")
            except Exception as te:
                logger.warning(f"Thumbnail extraction failed for {cid}: {te}")
                cand_thumb = None

            # Save render in database
            db.save_render(
                clip_id=cid,
                render_mode="shorts_9x16_blur",
                file_path=render_path,
            )

            # Update clip in database
            with db._connect() as conn:
                if cand_thumb:
                    conn.execute("UPDATE clips SET thumbnail_path = ?, render_path = ?, render_mode = ? WHERE id = ?", (cand_thumb, render_path, "shorts_9x16_blur", cid))
                else:
                    conn.execute("UPDATE clips SET render_path = ?, render_mode = ? WHERE id = ?", (render_path, "shorts_9x16_blur", cid))
                conn.commit()

            logger.info(f"Successfully processed and updated {cid}")

        except Exception as e:
            logger.exception(f"Failed to render {cid}: {e}")

    logger.info("All 4 clips processed!")

if __name__ == "__main__":
    main()
