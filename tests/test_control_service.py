import time

from fpv_ultimate.control_service import ControlService


class FakeServo:
    def __init__(self):
        self.angle = None


def test_apply_control_clamps_outputs():
    steer = FakeServo()
    throttle = FakeServo()
    service = ControlService(
        steer_servo=steer,
        throttle_servo=throttle,
        neutral_angle=90,
        failsafe_timeout=1,
    )

    service.apply_control(steer=-100, throttle=300, steer_speed=100, throttle_speed=100)

    assert steer.angle == 0
    assert throttle.angle == 180


def test_neutralize_returns_both_outputs_to_neutral():
    steer = FakeServo()
    throttle = FakeServo()
    service = ControlService(
        steer_servo=steer,
        throttle_servo=throttle,
        neutral_angle=90,
        failsafe_timeout=1,
    )

    service.apply_control(steer=0, throttle=180, steer_speed=100, throttle_speed=100)
    service.neutralize()

    assert steer.angle == 90
    assert throttle.angle == 90
    assert service.last_steer_angle == 90
    assert service.last_throttle_angle == 90


def test_failsafe_neutralizes_when_input_is_stale():
    steer = FakeServo()
    throttle = FakeServo()
    service = ControlService(
        steer_servo=steer,
        throttle_servo=throttle,
        neutral_angle=90,
        failsafe_timeout=0.001,
    )

    service.apply_control(steer=0, throttle=180, steer_speed=100, throttle_speed=100)
    time.sleep(0.01)

    assert service.apply_failsafe_if_needed(enabled=True) is True
    assert steer.angle == 90
    assert throttle.angle == 90


def test_failsafe_does_nothing_when_disabled():
    steer = FakeServo()
    throttle = FakeServo()
    service = ControlService(
        steer_servo=steer,
        throttle_servo=throttle,
        neutral_angle=90,
        failsafe_timeout=0.001,
    )

    service.apply_control(steer=0, throttle=180, steer_speed=100, throttle_speed=100)
    time.sleep(0.01)

    assert service.apply_failsafe_if_needed(enabled=False) is False
    assert steer.angle == 0
    assert throttle.angle == 180
