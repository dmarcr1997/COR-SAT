from __future__ import annotations

import json
import os
from datetime import datetime, timezone
import logging
import signal
import time
import sys
from pathlib import Path
from typing import Any

from sat_sdk import SatClient


CONFIG_PATH = Path(__file__).with_name("manifest.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

logger = logging.getLogger("periodic-camera")
shutdown_requested = False

HEARTBEAT_PATH = Path(
    os.environ["SAT_HEARTBEAT_PATH"]
)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def write_heartbeat() -> None:
    heartbeat = {
        "mission": os.environ["SAT_MISSION_NAME"],
        "pid": os.getpid(),
        "timestamp": utc_now(),
    }

    temporary_path = HEARTBEAT_PATH.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(heartbeat, indent=2),
        encoding="utf-8",
    )

    temporary_path.replace(HEARTBEAT_PATH)

def handle_shutdown(signum: int, frame: Any) -> None:
    global shutdown_requested
    logger.info("Shutdown requested by signal %s", signum)
    shutdown_requested = True


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)["configuration"]

    interval = config.get("capture_interval_seconds")
    if not isinstance(interval, (int, float)) or interval <= 0:
        raise ValueError("capture_interval_seconds must be greater than zero")

    timeout = config.get("request_timeout_seconds")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("request_timeout_seconds must be greater than zero")

    maximum_captures = config.get("maximum_captures")
    if maximum_captures is not None:
        if not isinstance(maximum_captures, int) or maximum_captures <= 0:
            raise ValueError("maximum_captures must be null or a positive integer")

    return config


def main() -> int:
    config = load_config()

    sat = SatClient(
        base_url=config["hal_base_url"],
    )

    interval = float(config["capture_interval_seconds"])
    maximum_captures = config["maximum_captures"]
    capture_count = 0

    logger.info("Starting periodic camera mission")

    while not shutdown_requested:
        try:
            write_heartbeat()
            image = sat.camera.capture()
            capture_count += 1

            logger.info(
                "Captured image %s: %s",
                image.filename,
                image.message,
            )
        except Exception:
            logger.exception("Camera capture failed")

        if maximum_captures is not None and capture_count >= maximum_captures:
            logger.info("Reached maximum capture count: %s", maximum_captures)
            break

        # Sleep in short increments so SIGTERM shutdown remains responsive.
        sleep_remaining = interval
        while sleep_remaining > 0 and not shutdown_requested:
            sleep_duration = min(0.25, sleep_remaining)
            time.sleep(sleep_duration)
            sleep_remaining -= sleep_duration

    logger.info("Periodic camera mission stopped")
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    raise SystemExit(main())
