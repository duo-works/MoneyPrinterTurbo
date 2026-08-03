from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
QUALITY_REJECTION_EXIT_CODE = 2
DEFAULT_RETRY_DELAY_SECONDS = 60


def run_until_published(
    command: Sequence[str],
    *,
    run_fn: Callable[..., Any] = subprocess.run,
    sleep_fn: Callable[[float], None] = time.sleep,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> int:
    attempt = 0
    while True:
        attempt += 1
        print(f"Quality-gated publication cycle {attempt} started.", flush=True)
        completed = run_fn(list(command), cwd=ROOT)
        if completed.returncode == 0:
            print("A publication cycle completed successfully.", flush=True)
            return 0
        if completed.returncode != QUALITY_REJECTION_EXIT_CODE:
            print(
                f"Publication stopped on operational exit code {completed.returncode}.",
                flush=True,
            )
            return int(completed.returncode)
        print(
            "Quality gate rejected every topic in this cycle; selecting new topics and retrying.",
            flush=True,
        )
        sleep_fn(retry_delay_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retry quality-rejected YouTube cycles until one video is published"
    )
    parser.add_argument("--not-before", metavar="HH:MM")
    args = parser.parse_args()
    command = [
        sys.executable,
        str(ROOT / "youtube_automation.py"),
        "--privacy",
        "public",
    ]
    if args.not_before:
        command.extend(["--not-before", args.not_before])
    raise SystemExit(run_until_published(command))


if __name__ == "__main__":
    main()