VIDEO_RESOLUTIONS = {
    "640x360": (640, 360),
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
}


def get_video_size(resolution_name: str, default_resolution: str = "1280x720") -> tuple[int, int]:
    return VIDEO_RESOLUTIONS.get(
        resolution_name,
        VIDEO_RESOLUTIONS[default_resolution],
    )


def clamp_fps(fps: int, minimum: int = 5, maximum: int = 60) -> int:
    return max(minimum, min(int(fps), maximum))
