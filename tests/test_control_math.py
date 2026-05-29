from fpv_ultimate.control_math import clamp, compute_alpha


def test_clamp_bounds_values():
    assert clamp(-10, 0, 180) == 0
    assert clamp(90, 0, 180) == 90
    assert clamp(250, 0, 180) == 180


def test_compute_alpha_clamps_speed_percent():
    assert compute_alpha(-50) == 0.1
    assert compute_alpha(0) == 0.1
    assert compute_alpha(100) == 1.0
    assert compute_alpha(150) == 1.0


def test_compute_alpha_handles_invalid_input():
    assert compute_alpha("not-a-number") == 1.0
