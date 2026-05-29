from fpv_ultimate.video_config import clamp_fps, get_video_size


def test_get_video_size_known_resolution():
    assert get_video_size("640x360") == (640, 360)
    assert get_video_size("1280x720") == (1280, 720)


def test_get_video_size_falls_back_to_default():
    assert get_video_size("bad-value", "640x360") == (640, 360)


def test_clamp_fps_bounds_values():
    assert clamp_fps(1) == 5
    assert clamp_fps(30) == 30
    assert clamp_fps(120) == 60
