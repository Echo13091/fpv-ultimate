import logging
import subprocess
import threading

logger = logging.getLogger("fpv-ultimate.system_actions")


def request_reboot() -> None:
    """Request a system reboot in a background thread."""
    logger.warning("Reboot requested")

    def _do_reboot():
        try:
            subprocess.Popen(["sudo", "reboot", "now"])
        except Exception as e:
            logger.error("Reboot command failed: %s", e)

    threading.Thread(target=_do_reboot, daemon=True).start()
