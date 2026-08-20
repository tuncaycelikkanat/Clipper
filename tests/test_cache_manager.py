import os
import tempfile
import time
from unittest.mock import patch
import pytest
from core.cache_manager import CacheManager

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td

def test_nonexistent_directory():
    manager = CacheManager(output_dir="/non/existent/path")
    assert manager.get_disk_usage() == {"total_bytes": 0, "clip_count": 0}
    manager.cleanup(max_age_days=7) # should not crash
    manager.clear_temp_files() # should not crash

def test_get_disk_usage(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    
    assert manager.get_disk_usage() == {"total_bytes": 0, "clip_count": 0}
    
    # Create fake files
    with open(os.path.join(temp_dir, "clip1.mp4"), "wb") as f:
        f.write(b"0" * 1024)
        
    subfolder = os.path.join(temp_dir, "channel_a")
    os.makedirs(subfolder, exist_ok=True)
    with open(os.path.join(subfolder, "clip2.mp4"), "wb") as f:
        f.write(b"0" * 2048)
        
    # Ignore raw_cut files
    with open(os.path.join(temp_dir, "raw_cut_temp.mp4"), "wb") as f:
        f.write(b"0" * 500)
        
    usage = manager.get_disk_usage()
    assert usage["clip_count"] == 2
    assert usage["total_bytes"] == 3072

def test_clear_temp_files(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    
    subfolder = os.path.join(temp_dir, "sub")
    os.makedirs(subfolder, exist_ok=True)

    paths = [
        os.path.join(temp_dir, "clip1.mp4"),
        os.path.join(temp_dir, "raw_cut_1.mp4"),
        os.path.join(subfolder, "raw_cut_2.mp4"),
        os.path.join(subfolder, "subs.ass")
    ]
    
    for p in paths:
        with open(p, "wb") as f:
            f.write(b"0")
            
    manager.clear_temp_files()
    
    assert os.path.exists(os.path.join(temp_dir, "clip1.mp4"))
    assert not os.path.exists(os.path.join(temp_dir, "raw_cut_1.mp4"))
    assert not os.path.exists(os.path.join(subfolder, "raw_cut_2.mp4"))
    assert not os.path.exists(os.path.join(subfolder, "subs.ass"))

def test_clear_temp_files_exception(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    p = os.path.join(temp_dir, "raw_cut_1.mp4")
    with open(p, "wb") as f:
        f.write(b"0")
    with patch("os.remove", side_effect=OSError("Permission denied")):
        manager.clear_temp_files() # should handle exception gracefully

def test_cleanup(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    
    subfolder = os.path.join(temp_dir, "channel_b")
    os.makedirs(subfolder, exist_ok=True)

    old_file = os.path.join(subfolder, "old.mp4")
    new_file = os.path.join(temp_dir, "new.mp4")
    
    with open(old_file, "wb") as f: f.write(b"1")
    with open(new_file, "wb") as f: f.write(b"1")
    
    past_time = time.time() - (10 * 24 * 60 * 60)
    os.utime(old_file, (past_time, past_time))
    
    manager.cleanup(max_age_days=7)
    
    assert not os.path.exists(old_file)
    assert os.path.exists(new_file)

def test_cleanup_exception(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    old_file = os.path.join(temp_dir, "old.mp4")
    with open(old_file, "wb") as f: f.write(b"1")
    past_time = time.time() - (10 * 24 * 60 * 60)
    os.utime(old_file, (past_time, past_time))
    with patch("os.remove", side_effect=OSError("Cannot delete")):
        manager.cleanup(max_age_days=7)

def test_clear_all(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    manager.clear_all() # safe to run
