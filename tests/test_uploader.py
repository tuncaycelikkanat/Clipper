import os
from unittest import mock
import pytest
from core.uploader import YouTubeUploader

def test_is_authenticated_false_when_no_token():
    uploader = YouTubeUploader(credentials_path="dummy_creds.json", token_path="non_existent_token.json")
    assert uploader.is_authenticated() is False

def test_generate_description_contains_hook():
    clip = {
        "hook_caption": "Wait for the end!",
        "category": "Gaming",
        "reason": "Epic fail",
        "start_formatted": "01:00",
        "end_formatted": "01:30"
    }
    desc = YouTubeUploader.generate_description(clip, "My Minecraft Stream")
    assert "Wait for the end!" in desc
    assert "Gaming" in desc
    assert "My Minecraft Stream" in desc
