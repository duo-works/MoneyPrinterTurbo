from pathlib import Path

from youtube_schedule import SCHEDULE_HOURS, build_schtasks_command


def test_schedule_has_four_evenly_spaced_istanbul_slots():
    assert SCHEDULE_HOURS == (2, 8, 14, 20)


def test_schtasks_command_runs_project_launcher_daily():
    command = build_schtasks_command(8, Path(r"C:\Project\MoneyPrinterTurbo"))

    assert command[:3] == ["schtasks.exe", "/Create", "/F"]
    assert "/SC" in command and command[command.index("/SC") + 1] == "DAILY"
    assert command[command.index("/ST") + 1] == "08:00"
    assert "MoneyPrinterTurbo-YouTube-08" in command
    assert "run_youtube_automation.cmd" in command[command.index("/TR") + 1]


def test_twenty_hour_slot_starts_production_at_1950_with_delayed_launcher():
    command = build_schtasks_command(20, Path(r"C:\Project\MoneyPrinterTurbo"))

    assert command[command.index("/ST") + 1] == "19:50"
    assert "run_youtube_automation_20.cmd" in command[command.index("/TR") + 1]
