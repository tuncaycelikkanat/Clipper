import glob
import os
import time

from core.logger import logger


class CacheManager:
    """Manages rendered files and temporary files cache."""

    def __init__(self, output_dir: str = "outputs/clips"):
        self.output_dir = output_dir

    def cleanup(self, max_age_days: int = 7) -> None:
        """Deletes render files older than max_age_days."""
        if not os.path.exists(self.output_dir):
            return

        now = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        deleted_count = 0

        for root, _, files in os.walk(self.output_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                if os.path.isfile(filepath):
                    file_age = now - os.path.getmtime(filepath)
                    if file_age > max_age_seconds:
                        try:
                            os.remove(filepath)
                            deleted_count += 1
                            logger.debug("Deleted old render file: {}", filepath)
                        except Exception as e:
                            logger.error("Failed to delete file {}: {}", filepath, e)

        logger.info("Cleaned up {} old render files", deleted_count)

    def get_disk_usage(self) -> dict:
        """Returns disk usage stats for the clips directory."""
        if not os.path.exists(self.output_dir):
            return {"total_bytes": 0, "clip_count": 0}

        total_bytes = 0
        clip_count = 0

        for root, _, files in os.walk(self.output_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                if os.path.isfile(filepath) and filename.endswith(".mp4") and not filename.startswith("raw_cut_"):
                    total_bytes += os.path.getsize(filepath)
                    clip_count += 1

        return {"total_bytes": total_bytes, "clip_count": clip_count}

    def clear_temp_files(self) -> None:
        """Deletes all temporary files (raw_cut_*.mp4 and *.ass) from output_dir."""
        if not os.path.exists(self.output_dir):
            return

        deleted_count = 0

        temp_patterns = [
            os.path.join(self.output_dir, "**", "raw_cut_*.mp4"),
            os.path.join(self.output_dir, "**", "*.ass"),
        ]

        for pattern in temp_patterns:
            for filepath in glob.glob(pattern, recursive=True):
                try:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.debug("Deleted temporary file: {}", filepath)
                except Exception as e:
                    logger.error("Failed to delete temp file {}: {}", filepath, e)

        logger.info("Cleared {} temporary files", deleted_count)

    def clear_all(self) -> None:
        """Deletes all rendered clips, thumbnails, and temp files from disk."""
        import shutil

        target_dirs = ["outputs/clips", "outputs/thumbnails"]
        for t_dir in target_dirs:
            if os.path.exists(t_dir):
                for item in os.listdir(t_dir):
                    item_path = os.path.join(t_dir, item)
                    try:
                        if os.path.isfile(item_path) or os.path.islink(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                    except Exception as e:
                        logger.error("Failed to delete {}: {}", item_path, e)
        logger.info("Completely cleared all output files from disk.")
