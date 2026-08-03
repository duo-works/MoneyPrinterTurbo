from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCHEDULE_HOURS = (2, 8, 14, 20)
TASK_PREFIX = "MoneyPrinterTurbo-YouTube"


def task_name(hour: int) -> str:
    if hour not in SCHEDULE_HOURS:
        raise ValueError(f"unsupported schedule hour: {hour}")
    return f"{TASK_PREFIX}-{hour:02d}"


def build_schtasks_command(hour: int, project_root: Path = ROOT) -> list[str]:
    launcher_name = (
        "run_youtube_automation_20.cmd"
        if hour == 20
        else "run_youtube_automation.cmd"
    )
    launcher = (project_root / launcher_name).resolve()
    start_time = "19:50" if hour == 20 else f"{hour:02d}:00"
    return [
        "schtasks.exe",
        "/Create",
        "/F",
        "/TN",
        task_name(hour),
        "/TR",
        str(launcher),
        "/SC",
        "DAILY",
        "/ST",
        start_time,
        "/RL",
        "LIMITED",
    ]


def install_schedule(project_root: Path = ROOT) -> list[dict[str, Any]]:
    results = []
    for hour in SCHEDULE_HOURS:
        completed = subprocess.run(
            build_schtasks_command(hour, project_root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=60,
        )
        if completed.returncode:
            raise RuntimeError(
                f"could not create task {task_name(hour)}: {completed.stdout} {completed.stderr}"
            )
        results.append({"task": task_name(hour), "time": f"{hour:02d}:00"})
    return results


def remove_schedule() -> list[str]:
    removed = []
    for hour in SCHEDULE_HOURS:
        name = task_name(hour)
        completed = subprocess.run(
            ["schtasks.exe", "/Delete", "/F", "/TN", name],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=60,
        )
        if completed.returncode == 0:
            removed.append(name)
    return removed


def query_schedule() -> list[dict[str, str]]:
    results = []
    for hour in SCHEDULE_HOURS:
        name = task_name(hour)
        completed = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", name, "/FO", "LIST", "/V"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=60,
        )
        results.append(
            {
                "task": name,
                "configured": str(completed.returncode == 0).lower(),
                "time": f"{hour:02d}:00",
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the four daily YouTube automation tasks")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--install", action="store_true")
    action.add_argument("--remove", action="store_true")
    action.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.install:
        result = install_schedule()
    elif args.remove:
        result = remove_schedule()
    else:
        result = query_schedule()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
