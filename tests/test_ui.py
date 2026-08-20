"""Tests for Streamlit UI navigation and page rendering."""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


def test_main_app_navigation():
    """Test that ui/app.py loads and configures navigation without error."""
    at = AppTest.from_file(str(ROOT / "ui" / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"UI threw exception: {at.exception}"


def test_analyze_page():
    """Test that ui/app_pages/analyze.py renders properly without crash."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "analyze.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"Analyze page error: {at.exception}"


def test_clips_page():
    """Test that ui/app_pages/clips.py renders properly."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "clips.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"Clips page error: {at.exception}"


def test_export_page():
    """Test that ui/app_pages/export.py renders properly."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "export.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"Export page error: {at.exception}"


def test_settings_page():
    """Test that ui/app_pages/settings.py renders properly."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "settings.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"Settings page error: {at.exception}"
