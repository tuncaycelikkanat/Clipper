"""CLI entry point for the clipper project.

Usage examples::

    python -m clipper run --url "https://youtu.be/dQw4w9WgXcQ"
    python -m clipper run --url "dQw4w9WgXcQ" --clips 5 --format shorts_9x16_black
    python -m clipper run --url "https://youtu.be/dQw4w9WgXcQ" --no-subtitles --no-hook
"""

import argparse
import sys

from core.logger import logger
from core.pipeline import ClipperPipeline

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
RENDER_MODES = [
    "square_1x1_black",
    "shorts_9x16_black",
    "shorts_9x16_blur",
    "original_16x9",
]


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="clipper",
        description="Autonomous YouTube Gaming Clip Extractor & Editor",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -----------------------------------------------------------------
    # Sub-command: run
    # -----------------------------------------------------------------
    run_parser = sub.add_parser(
        "run",
        help="Run the full pipeline for a YouTube URL and produce edited clips.",
    )
    run_parser.add_argument(
        "--url",
        required=True,
        metavar="URL",
        help="YouTube video URL or 11-character video ID.",
    )
    run_parser.add_argument(
        "--clips",
        type=int,
        default=3,
        metavar="N",
        dest="target_clips",
        help="Number of clips to extract (default: 3).",
    )
    run_parser.add_argument(
        "--format",
        choices=RENDER_MODES,
        default="square_1x1_black",
        dest="render_mode",
        help="Output aspect-ratio preset (default: square_1x1_black).",
    )
    run_parser.add_argument(
        "--no-subtitles",
        action="store_false",
        dest="add_subtitles",
        default=True,
        help="Disable Karaoke subtitle burn-in.",
    )
    run_parser.add_argument(
        "--no-hook",
        action="store_false",
        dest="add_hook_card",
        default=True,
        help="Disable the first-3-second hook title card.",
    )
    run_parser.add_argument(
        "--no-color",
        action="store_false",
        dest="enhance_colors",
        default=True,
        help="Disable vibrancy/contrast colour grading.",
    )
    run_parser.add_argument(
        "--api-key",
        default=None,
        metavar="KEY",
        help="Gemini API key (overrides GEMINI_API_KEY env var).",
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace) -> int:
    """Execute the pipeline and print results."""
    logger.info(
        "Starting pipeline — url={} clips={} format={}",
        args.url,
        args.target_clips,
        args.render_mode,
    )

    def _progress(msg: str) -> None:
        print(msg, flush=True)

    try:
        results = ClipperPipeline.run(
            url=args.url,
            target_clips=args.target_clips,
            render_mode=args.render_mode,
            add_subtitles=args.add_subtitles,
            add_hook_card=args.add_hook_card,
            enhance_colors=args.enhance_colors,
            api_key=args.api_key,
            progress_callback=_progress,
        )
    except Exception as exc:
        logger.error("Pipeline failed: {}", exc)
        print(f"\n❌ Pipeline error: {exc}", file=sys.stderr)
        return 1

    print("\n" + "=" * 60)
    print(f"✅  {len(results)} clip(s) rendered successfully:")
    print("=" * 60)
    for clip in results:
        print(
            f"  [{clip['rank']}] {clip['title']}\n"
            f"       {clip['start_time']}s → {clip['end_time']}s  "
            f"({clip['duration']}s)  score={clip['score']}\n"
            f"       ▶ {clip['render_path']}\n"
        )
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and dispatch to the appropriate sub-command."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        sys.exit(_cmd_run(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
