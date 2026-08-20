import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from core.aligner import AlignmentEngine

@patch('core.aligner._SCENE_DETECTOR_AVAILABLE', True)
@patch('core.aligner.SceneDetector')
def test_aligner_scene_cuts_success(mock_scene_detector):
    mock_scene_detector.snap_to_scene_boundary.side_effect = [5.0, 25.0] # start, end
    
    start, end = AlignmentEngine.refine_cut_points(
        start_time=10.0,
        end_time=20.0,
        times=np.array([]),
        rms=np.array([]),
        transcript=[],
        max_drift_sec=3.0,
        scene_cuts=[5.0, 15.0, 25.0]
    )
    
    assert start == 5.0
    assert end == 25.0

@patch('core.aligner._SCENE_DETECTOR_AVAILABLE', True)
@patch('core.aligner.SceneDetector')
def test_aligner_scene_cuts_fallback(mock_scene_detector):
    # Scene cuts result in < 10.0 duration, should fall back to next priority (which is empty here, then audio which is empty, so falls back to original)
    mock_scene_detector.snap_to_scene_boundary.side_effect = [10.0, 12.0]
    
    start, end = AlignmentEngine.refine_cut_points(
        start_time=10.0,
        end_time=20.0,
        times=np.array([]),
        rms=np.array([]),
        transcript=[],
        max_drift_sec=3.0,
        scene_cuts=[10.0, 12.0]
    )
    
    assert start == 10.0
    assert end == 20.0

@patch('core.aligner.TranscriptManager')
def test_aligner_transcript(mock_tm):
    mock_tm.snap_boundaries.return_value = (8.0, 22.0, "Text")
    
    start, end = AlignmentEngine.refine_cut_points(
        start_time=10.0,
        end_time=20.0,
        times=np.array([]),
        rms=np.array([]),
        transcript=[{"text": "dummy"}],
        max_drift_sec=3.0,
        scene_cuts=None
    )
    
    assert start == 8.0
    assert end == 22.0
    mock_tm.snap_boundaries.assert_called_once()

def test_aligner_audio_empty():
    start, end = AlignmentEngine.refine_cut_points(
        start_time=10.0,
        end_time=20.0,
        times=np.array([]),
        rms=np.array([]),
        transcript=[],
        max_drift_sec=3.0,
        scene_cuts=None
    )
    assert start == 10.0
    assert end == 20.0

def test_aligner_audio_dips_success():
    times = np.array([7.0, 9.0, 10.0, 12.0, 18.0, 20.0, 21.0, 23.0])
    # Dips at 9.0 (0.1) and 21.0 (0.1)
    rms = np.array([0.5, 0.1, 0.5, 0.6, 0.6, 0.5, 0.1, 0.6])
    
    start, end = AlignmentEngine.refine_cut_points(
        start_time=10.0,
        end_time=20.0,
        times=times,
        rms=rms,
        transcript=[],
        max_drift_sec=3.0,
        scene_cuts=None
    )
    
    assert start == 9.0
    assert end == 21.0

def test_aligner_audio_dips_fallback_short():
    times = np.array([9.0, 10.0, 11.0, 19.0, 20.0, 21.0])
    rms = np.array([0.5, 0.1, 0.5, 0.5, 0.1, 0.5])
    
    # candidate 10 to 12.
    # start snaps to 10.0, end snaps to 11.0 or whatever, but duration < 10.
    # original is 10.0 to 12.0 (duration 2.0). 
    start, end = AlignmentEngine.refine_cut_points(
        start_time=10.0,
        end_time=12.0, # small duration
        times=times,
        rms=rms,
        transcript=[],
        max_drift_sec=3.0,
        scene_cuts=None
    )
    
    assert start == 10.0
    assert end == 12.0

def test_aligner_audio_dips_no_mask_match():
    # times way outside bounds
    times = np.array([100.0, 200.0])
    rms = np.array([0.1, 0.1])
    
    start, end = AlignmentEngine.refine_cut_points(
        start_time=10.0,
        end_time=20.0,
        times=times,
        rms=rms,
        transcript=[],
        max_drift_sec=3.0,
        scene_cuts=None
    )
    
    assert start == 10.0
    assert end == 20.0
