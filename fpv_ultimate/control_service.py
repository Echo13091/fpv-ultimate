import logging
import threading
import time

from fpv_ultimate.control_math import clamp, compute_alpha

logger = logging.getLogger("fpv-ultimate.control_service")


class ControlService:
    """Owns steering/throttle servo output state and failsafe behavior."""

    def __init__(
        self,
        *,
        steer_servo,
        throttle_servo,
        neutral_angle: float = 90.0,
        failsafe_timeout: float = 0.25,
    ):
        self.steer_servo = steer_servo
        self.throttle_servo = throttle_servo
        self.neutral_angle = float(neutral_angle)
        self.failsafe_timeout = float(failsafe_timeout)

        self.last_control_time = time.time()
        self.last_steer_angle = self.neutral_angle
        self.last_throttle_angle = self.neutral_angle
        self._lock = threading.Lock()

    def neutralize(self) -> None:
        """Return steering and throttle to neutral."""
        with self._lock:
            self.last_steer_angle = self.neutral_angle
            self.last_throttle_angle = self.neutral_angle
            self.steer_servo.angle = self.neutral_angle
            self.throttle_servo.angle = self.neutral_angle

    def apply_control(
        self,
        *,
        steer,
        throttle,
        steer_speed: float = 100.0,
        throttle_speed: float = 100.0,
    ) -> None:
        """Apply smoothed steering/throttle commands to the servos."""
        steer = clamp(float(steer), 0.0, 180.0)
        throttle = clamp(float(throttle), 0.0, 180.0)

        steer_alpha = compute_alpha(steer_speed)
        throttle_alpha = compute_alpha(throttle_speed)

        with self._lock:
            self.last_steer_angle = (
                (1.0 - steer_alpha) * self.last_steer_angle
                + steer_alpha * steer
            )
            self.last_throttle_angle = (
                (1.0 - throttle_alpha) * self.last_throttle_angle
                + throttle_alpha * throttle
            )

            self.steer_servo.angle = self.last_steer_angle
            self.throttle_servo.angle = self.last_throttle_angle
            self.last_control_time = time.time()

    def apply_failsafe_if_needed(self, *, enabled: bool) -> bool:
        """Neutralize outputs if failsafe is enabled and control input is stale."""
        if not enabled:
            return False

        with self._lock:
            if time.time() - self.last_control_time <= self.failsafe_timeout:
                return False

            self.last_steer_angle = self.neutral_angle
            self.last_throttle_angle = self.neutral_angle
            self.steer_servo.angle = self.neutral_angle
            self.throttle_servo.angle = self.neutral_angle
            return True
