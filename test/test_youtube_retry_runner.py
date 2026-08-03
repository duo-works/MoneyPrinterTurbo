from types import SimpleNamespace

from youtube_retry_runner import run_until_published


def test_quality_rejections_retry_until_a_video_is_published():
    results = iter([SimpleNamespace(returncode=2), SimpleNamespace(returncode=2), SimpleNamespace(returncode=0)])
    commands = []
    delays = []

    def run(command, **kwargs):
        commands.append((list(command), kwargs))
        return next(results)

    exit_code = run_until_published(
        ["python", "youtube_automation.py", "--privacy", "public"],
        run_fn=run,
        sleep_fn=delays.append,
        retry_delay_seconds=60,
    )

    assert exit_code == 0
    assert len(commands) == 3
    assert delays == [60, 60]


def test_operational_failure_is_not_mislabeled_as_quality_rejection():
    calls = []

    def run(command, **kwargs):
        calls.append((list(command), kwargs))
        return SimpleNamespace(returncode=1)

    exit_code = run_until_published(
        ["python", "youtube_automation.py"],
        run_fn=run,
        sleep_fn=lambda _seconds: (_ for _ in ()).throw(
            AssertionError("operational failures must not enter the quality retry loop")
        ),
    )

    assert exit_code == 1
    assert len(calls) == 1
