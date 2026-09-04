from unittest import mock

from core.scene_detector import SceneDetector


def test_snap_to_scene_boundary_snaps_correctly():
    scene_cuts = [10.5, 20.0, 30.5]

    # Within snap range
    snapped = SceneDetector.snap_to_scene_boundary(21.0, scene_cuts, max_snap_sec=2.0)
    assert snapped == 20.0

    snapped2 = SceneDetector.snap_to_scene_boundary(9.0, scene_cuts, max_snap_sec=2.0)
    assert snapped2 == 10.5


def test_snap_to_scene_boundary_no_nearby_cut():
    scene_cuts = [10.5, 20.0, 30.5]

    # Outside snap range
    snapped = SceneDetector.snap_to_scene_boundary(25.0, scene_cuts, max_snap_sec=2.0)
    assert snapped == 25.0

    # Empty scene_cuts
    snapped_empty = SceneDetector.snap_to_scene_boundary(15.0, [], max_snap_sec=2.0)
    assert snapped_empty == 15.0


def test_detect_scenes_returns_list():
    with mock.patch("core.scene_detector.subprocess.run") as mock_run:
        mock_result = mock.Mock()
        mock_result.stderr = (
            b"[Parsed_scdet_0 @ 0xADDR] lavfi.scd.score: 45.23, lavfi.scd.time: 12.083\n"
            b"[Parsed_scdet_0 @ 0xADDR] lavfi.scd.score: 35.10, lavfi.scd.time: 25.400\n"
            b"[Parsed_scdet_0 @ 0xADDR] lavfi.scd.time: ..\n"
        )
        mock_run.return_value = mock_result

        cuts = SceneDetector.detect_scenes("dummy.mp4", threshold=30.0)

        assert len(cuts) == 2
        assert cuts[0] == 12.083
        assert cuts[1] == 25.400


def test_detect_scenes_filenotfound():
    with mock.patch("core.scene_detector.subprocess.run", side_effect=FileNotFoundError):
        cuts = SceneDetector.detect_scenes("dummy.mp4")
        assert cuts == []


def test_detect_scenes_generic_exception():
    with mock.patch("core.scene_detector.subprocess.run", side_effect=RuntimeError("Boom")):
        cuts = SceneDetector.detect_scenes("dummy.mp4")
        assert cuts == []
