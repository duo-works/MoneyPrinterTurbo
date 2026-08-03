from datetime import datetime, timezone

import pytest

from youtube_channel_analyzer import (
    build_video_records,
    parse_iso8601_duration,
    recommend_publish_hours,
)


def test_parse_iso8601_duration_supports_hours_minutes_and_seconds():
    assert parse_iso8601_duration("PT38S") == 38
    assert parse_iso8601_duration("PT1M2S") == 62
    assert parse_iso8601_duration("PT1H2M3S") == 3723


def test_build_video_records_joins_analytics_and_filters_to_short_form():
    videos = [
        {
            "id": "short1",
            "snippet": {
                "title": "A short history fact",
                "publishedAt": "2026-07-20T10:00:00Z",
            },
            "contentDetails": {"duration": "PT39S"},
            "statistics": {"viewCount": "1000", "likeCount": "80", "commentCount": "20"},
        },
        {
            "id": "long1",
            "snippet": {
                "title": "A long documentary",
                "publishedAt": "2026-07-19T10:00:00Z",
            },
            "contentDetails": {"duration": "PT8M"},
            "statistics": {"viewCount": "5000", "likeCount": "100", "commentCount": "10"},
        },
    ]
    analytics = {
        "short1": {
            "views": 900,
            "averageViewPercentage": 82.5,
            "subscribersGained": 12,
        }
    }

    records = build_video_records(
        videos,
        analytics,
        now=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )

    assert [record["video_id"] for record in records] == ["short1"]
    assert records[0]["duration_seconds"] == 39
    assert records[0]["engagement_rate"] == pytest.approx(0.10)
    assert records[0]["average_view_percentage"] == 82.5
    assert records[0]["subscribers_gained"] == 12


def test_recommend_publish_hours_uses_even_global_test_slots_when_history_is_sparse():
    records = [
        {"published_hour_local": 19, "performance_score": 100.0},
        {"published_hour_local": 13, "performance_score": 50.0},
        {"published_hour_local": 22, "performance_score": 25.0},
    ]

    assert recommend_publish_hours(records, count=4) == [2, 8, 14, 20]
