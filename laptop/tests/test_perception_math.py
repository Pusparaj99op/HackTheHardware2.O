import math

import numpy as np
import pytest

from visionpilot.perception.aruco import pose_from_corners
from visionpilot.perception.free_space import FreeSpaceParams, column_openness

FS = FreeSpaceParams()


def floor_scene(height=90, width=160):
    """Disparity of an empty floor seen by a low forward camera.

    Above the horizon (mid-frame) everything is far (~0). Below it, floor
    disparity grows linearly with the row, reaching 1.0 at the bottom edge.
    """
    rows = np.arange(height, dtype=np.float32) / (height - 1)
    disparity = np.clip((rows - 0.5) / 0.5, 0.0, 1.0) + 0.02
    return np.repeat(disparity[:, None], width, axis=1)


def test_clear_corridor_is_open_everywhere():
    openness = column_openness(floor_scene(), FS)
    assert len(openness) == FS.columns
    assert all(o > 0.8 for o in openness)


def test_close_object_in_center_closes_center_column():
    scene = floor_scene()
    h, w = scene.shape
    scene[int(h * 0.3) : int(h * 0.8), int(w * 0.42) : int(w * 0.58)] = 0.9
    openness = column_openness(scene, FS)
    assert openness[2] < 0.1
    assert openness[0] > 0.8
    assert openness[4] > 0.8


def test_degenerate_depth_is_treated_as_blocked():
    assert column_openness(np.zeros((90, 160), dtype=np.float32), FS) == (0.0,) * FS.columns


def test_marker_pose_heading_points_to_top_edge():
    # axis-aligned marker, top edge (corners 0->1) facing up on screen
    corners = np.array([[90, 90], [110, 90], [110, 110], [90, 110]], dtype=np.float32)
    pose = pose_from_corners(corners, width=200, height=200)
    assert pose.x == pytest.approx(0.5)
    assert pose.y == pytest.approx(0.5)
    assert pose.heading == pytest.approx(-math.pi / 2)
    assert pose.size == pytest.approx(0.1)


def test_marker_rotated_to_face_right():
    # top edge on the right side -> car points right (heading 0)
    corners = np.array([[110, 90], [110, 110], [90, 110], [90, 90]], dtype=np.float32)
    assert pose_from_corners(corners, width=200, height=200).heading == pytest.approx(0)
