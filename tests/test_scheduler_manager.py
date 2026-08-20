import pytest
import datetime
from unittest.mock import patch, MagicMock

import core.scheduler_manager

# Mock missing APScheduler imports
core.scheduler_manager._APSCHEDULER_AVAILABLE = True
core.scheduler_manager.BackgroundScheduler = MagicMock()
core.scheduler_manager.IntervalTrigger = MagicMock()

from core.scheduler_manager import SchedulerManager

def test_scheduler_init_no_apscheduler():
    with patch("core.scheduler_manager._APSCHEDULER_AVAILABLE", False):
        with pytest.raises(ImportError, match="APScheduler kurulu değil"):
            SchedulerManager()

def test_scheduler_lifecycle():
    sm = SchedulerManager()
    
    with patch.object(sm._scheduler, "start") as mock_start, \
         patch.object(sm._scheduler, "shutdown") as mock_shutdown:
        
        sm._scheduler.running = False
        sm.start()
        mock_start.assert_called_once()

        sm._scheduler.running = True
        sm.start()
        assert mock_start.call_count == 1

        sm.stop()
        mock_shutdown.assert_called_once_with(wait=True)
        
        sm._scheduler.running = False
        sm.stop()
        assert mock_shutdown.call_count == 1

def test_add_remove_list_jobs():
    sm = SchedulerManager()
    
    with patch.object(sm._scheduler, "add_job") as mock_add, \
         patch.object(sm._scheduler, "get_job") as mock_get_job, \
         patch.object(sm._scheduler, "remove_job") as mock_remove_job, \
         patch.object(sm._scheduler, "get_jobs") as mock_get_jobs, \
         patch("core.scheduler_manager.uuid.uuid4") as mock_uuid:
         
        mock_uuid.return_value.hex = "1234567890"

        # Test add_job without ID
        mock_get_job.return_value = None
        job_id = sm.add_channel_job("http://youtube.com/c/test", 12)
        assert job_id == "channel_12345678"
        assert job_id in sm._job_registry
        mock_add.assert_called_once()
        
        # Test add_job duplicate
        mock_get_job.return_value = True
        with pytest.raises(RuntimeError, match="zaten mevcut"):
            sm.add_channel_job("http://youtube.com/c/test", 12, job_id=job_id)

        # Test list_jobs
        mock_job = MagicMock()
        mock_job.id = job_id
        mock_job.name = "TestName"
        mock_job.next_run_time = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
        mock_job.trigger = "interval"
        
        mock_job2 = MagicMock()
        mock_job2.id = "unknown_job"
        mock_job2.name = "Unknown"
        mock_job2.next_run_time = None
        mock_job2.trigger = "interval"

        mock_get_jobs.return_value = [mock_job, mock_job2]
        
        jobs = sm.list_jobs()
        assert len(jobs) == 2
        assert jobs[0]["id"] == job_id
        assert jobs[0]["channel_url"] == "http://youtube.com/c/test"
        assert jobs[0]["next_run"] == mock_job.next_run_time.isoformat()
        
        assert jobs[1]["id"] == "unknown_job"
        assert jobs[1]["channel_url"] == ""
        assert jobs[1]["next_run"] == ""

        # Test remove_job
        mock_get_job.return_value = True
        sm.remove_job(job_id)
        mock_remove_job.assert_called_once_with(job_id)
        assert job_id not in sm._job_registry
        
        # Test remove_job not found
        mock_get_job.return_value = None
        with pytest.raises(KeyError, match="Job bulunamadı"):
            sm.remove_job("invalid")

def test_get_status():
    sm = SchedulerManager()
    with patch.object(sm._scheduler, "get_jobs") as mock_get_jobs:
        sm._scheduler.running = True
        mock_get_jobs.return_value = [MagicMock(), MagicMock()]
        status = sm.get_status()
        assert status["running"] is True
        assert status["job_count"] == 2

@patch("core.feed.ChannelFeed")
@patch("core.scheduler_manager.DatabaseManager")
def test_run_channel_check_success_with_new_videos(mock_db_class, mock_feed_class):
    sm = SchedulerManager()
    
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.get_processed_video_ids.return_value = ["vid1"]
    
    mock_feed_class.get_new_videos.return_value = [{"id": "vid2"}]
    
    callback_called = False
    def my_cb(url, videos):
        nonlocal callback_called
        callback_called = True
        assert url == "url"
        assert videos == [{"id": "vid2"}]
        
    sm.on_new_videos = my_cb
    sm._run_channel_check("url")
    assert callback_called
    mock_feed_class.get_new_videos.assert_called_once_with("url", processed_ids=["vid1"], max_count=10)

@patch("core.feed.ChannelFeed")
@patch("core.scheduler_manager.DatabaseManager")
def test_run_channel_check_no_new_videos(mock_db_class, mock_feed_class):
    sm = SchedulerManager()
    
    mock_feed_class.get_new_videos.return_value = []
    
    callback_called = False
    def my_cb(url, videos):
        nonlocal callback_called
        callback_called = True
        
    sm.on_new_videos = my_cb
    sm._run_channel_check("url")
    assert not callback_called

@patch("core.feed.ChannelFeed")
@patch("core.scheduler_manager.DatabaseManager")
def test_run_channel_check_db_error(mock_db_class, mock_feed_class):
    sm = SchedulerManager()
    
    mock_db_class.side_effect = Exception("DB error")
    mock_feed_class.get_new_videos.return_value = [{"id": "vid2"}]
    
    callback_called = False
    def my_cb(url, videos):
        nonlocal callback_called
        callback_called = True
        
    sm.on_new_videos = my_cb
    sm._run_channel_check("url")
    assert callback_called
    # When DB errors, processed_ids should be []
    mock_feed_class.get_new_videos.assert_called_once_with("url", processed_ids=[], max_count=10)

@patch("core.feed.ChannelFeed")
def test_run_channel_check_db_none(mock_feed_class):
    with patch("core.scheduler_manager.DatabaseManager", None):
        sm = SchedulerManager()
        mock_feed_class.get_new_videos.return_value = [{"id": "vid2"}]
        
        callback_called = False
        def my_cb(url, videos):
            nonlocal callback_called
            callback_called = True
            
        sm.on_new_videos = my_cb
        sm._run_channel_check("url")
        assert callback_called

@patch("core.feed.ChannelFeed")
def test_run_channel_check_exception(mock_feed_class):
    sm = SchedulerManager()
    mock_feed_class.get_new_videos.side_effect = Exception("Feed failed")
    
    # Should not raise
    sm._run_channel_check("url")

def test_imports_success():
    import sys
    import importlib
    
    mock_apscheduler = MagicMock()
    mock_apscheduler_bg = MagicMock()
    mock_apscheduler_trigger = MagicMock()
    
    sys.modules["apscheduler"] = mock_apscheduler
    sys.modules["apscheduler.schedulers.background"] = mock_apscheduler_bg
    sys.modules["apscheduler.triggers.interval"] = mock_apscheduler_trigger
    
    # Reload to hit try blocks
    import core.scheduler_manager
    importlib.reload(core.scheduler_manager)
    
    assert core.scheduler_manager._APSCHEDULER_AVAILABLE is True
    assert core.scheduler_manager.DatabaseManager is not None
    assert core.scheduler_manager.logger is not None
    
    # Clean up
    del sys.modules["apscheduler"]
    del sys.modules["apscheduler.schedulers.background"]
    del sys.modules["apscheduler.triggers.interval"]

def test_imports_fail():
    import sys
    import importlib
    
    # Hide modules to force ImportError
    orig_logger = sys.modules.get("core.logger")
    orig_db = sys.modules.get("core.database")
    
    sys.modules["core.logger"] = None
    sys.modules["core.database"] = None
    
    import core.scheduler_manager
    importlib.reload(core.scheduler_manager)
    
    assert core.scheduler_manager.DatabaseManager is None
    # logger should fallback to logging.getLogger
    assert core.scheduler_manager.logger.name == "core.scheduler_manager"
    
    # Restore
    if orig_logger:
        sys.modules["core.logger"] = orig_logger
    else:
        del sys.modules["core.logger"]
        
    if orig_db:
        sys.modules["core.database"] = orig_db
    else:
        del sys.modules["core.database"]
