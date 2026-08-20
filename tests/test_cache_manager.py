import os
import tempfile
import time
import pytest
from core.cache_manager import CacheManager

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td

def test_get_disk_usage(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    
    assert manager.get_disk_usage() == {"total_bytes": 0, "clip_count": 0}
    
    # Create fake files
    with open(os.path.join(temp_dir, "clip1.mp4"), "wb") as f:
        f.write(b"0" * 1024)
        
    with open(os.path.join(temp_dir, "clip2.mp4"), "wb") as f:
        f.write(b"0" * 2048)
        
    # Ignore raw_cut files
    with open(os.path.join(temp_dir, "raw_cut_temp.mp4"), "wb") as f:
        f.write(b"0" * 500)
        
    usage = manager.get_disk_usage()
    assert usage["clip_count"] == 2
    assert usage["total_bytes"] == 3072

def test_clear_temp_files(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    
    paths = [
        os.path.join(temp_dir, "clip1.mp4"),
        os.path.join(temp_dir, "raw_cut_1.mp4"),
        os.path.join(temp_dir, "raw_cut_2.mp4"),
        os.path.join(temp_dir, "subs.ass")
    ]
    
    for p in paths:
        with open(p, "wb") as f:
            f.write(b"0")
            
    manager.clear_temp_files()
    
    assert os.path.exists(os.path.join(temp_dir, "clip1.mp4"))
    assert not os.path.exists(os.path.join(temp_dir, "raw_cut_1.mp4"))
    assert not os.path.exists(os.path.join(temp_dir, "raw_cut_2.mp4"))
    assert not os.path.exists(os.path.join(temp_dir, "subs.ass"))

def test_cleanup(temp_dir):
    manager = CacheManager(output_dir=temp_dir)
    
    # Create two files
    old_file = os.path.join(temp_dir, "old.mp4")
    new_file = os.path.join(temp_dir, "new.mp4")
    
    with open(old_file, "wb") as f: f.write(b"1")
    with open(new_file, "wb") as f: f.write(b"1")
    
    # Set old_file mtime to 10 days ago
    past_time = time.time() - (10 * 24 * 60 * 60)
    os.utime(old_file, (past_time, past_time))
    
    manager.cleanup(max_age_days=7)
    
    assert not os.path.exists(old_file)
    assert os.path.exists(new_file)
