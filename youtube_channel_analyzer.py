from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
ROOT = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = ROOT / "client_secret.json"
TOKEN_FILE = ROOT / "youtube_analytics_token.json"
DEFAULT_TIMEZONE = "Europe/Istanbul"
DEFAULT_PUBLISH_HOURS = [2, 8, 14, 20]


def parse_iso8601_duration(value: str) -> int:
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?",
        value or "",
    )
    if not match:
        return 0
    parts = {name: int(raw or 0) for name, raw in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        result = float(value or 0)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_video_records(
    video_items: list[dict[str, Any]],
    analytics_by_video: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
    timezone_name: str = "UTC",
) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    local_tz = ZoneInfo(timezone_name)
    records: list[dict[str, Any]] = []

    for item in video_items:
        duration_seconds = parse_iso8601_duration(
            item.get("contentDetails", {}).get("duration", "")
        )
        if not 0 < duration_seconds <= 180:
            continue

        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        analytics = analytics_by_video.get(item.get("id", ""), {})
        published_at = datetime.fromisoformat(
            snippet.get("publishedAt", "1970-01-01T00:00:00Z").replace("Z", "+00:00")
        )
        age_days = max((now - published_at).total_seconds() / 86400, 1.0)
        public_views = _as_int(statistics.get("viewCount"))
        views = _as_int(analytics.get("views", public_views))
        likes = _as_int(analytics.get("likes", statistics.get("likeCount")))
        comments = _as_int(analytics.get("comments", statistics.get("commentCount")))
        average_view_percentage = _as_float(analytics.get("averageViewPercentage"))
        subscribers_gained = _as_int(analytics.get("subscribersGained"))
        has_analytics_engagement = "likes" in analytics or "comments" in analytics
        engagement_views = views if has_analytics_engagement else public_views
        engagement_rate = (
            (likes + comments) / engagement_views if engagement_views else 0.0
        )
        views_per_day = views / age_days
        retention_multiplier = 0.5 + min(average_view_percentage, 150.0) / 100.0
        performance_score = views_per_day * retention_multiplier * (1 + engagement_rate * 5)

        records.append(
            {
                "video_id": item.get("id", ""),
                "title": snippet.get("title", ""),
                "published_at": published_at.isoformat(),
                "published_hour_local": published_at.astimezone(local_tz).hour,
                "duration_seconds": duration_seconds,
                "views": views,
                "likes": likes,
                "comments": comments,
                "engagement_rate": engagement_rate,
                "average_view_duration": _as_float(analytics.get("averageViewDuration")),
                "average_view_percentage": average_view_percentage,
                "subscribers_gained": subscribers_gained,
                "views_per_day": views_per_day,
                "performance_score": performance_score,
                "url": f"https://youtube.com/shorts/{item.get('id', '')}",
            }
        )

    return sorted(records, key=lambda record: record["performance_score"], reverse=True)


def recommend_publish_hours(records: list[dict[str, Any]], count: int = 4) -> list[int]:
    # With fewer than eight uploads, hour-by-hour conclusions are noise rather
    # than evidence. Use four evenly spaced global test slots until the channel
    # has enough history for a meaningful comparison.
    if len(records) < 8:
        return DEFAULT_PUBLISH_HOURS[:count]

    grouped: dict[int, list[float]] = defaultdict(list)
    for record in records:
        hour = _as_int(record.get("published_hour_local")) % 24
        grouped[hour].append(_as_float(record.get("performance_score")))

    ranked = sorted(
        grouped,
        key=lambda hour: (sum(grouped[hour]) / len(grouped[hour]), len(grouped[hour])),
        reverse=True,
    )
    selected: list[int] = []
    for hour in [*ranked, *DEFAULT_PUBLISH_HOURS]:
        if hour not in selected:
            selected.append(hour)
        if len(selected) == count:
            break
    return selected


def get_credentials(authorize_only: bool = False) -> Credentials:
    credentials = None
    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        if not CLIENT_SECRET_FILE.exists():
            raise FileNotFoundError(f"Missing OAuth client file: {CLIENT_SECRET_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
        credentials = flow.run_local_server(port=0, open_browser=True)
        TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    if authorize_only:
        print("YouTube read-only authorization is ready.")
    return credentials


def fetch_channel_and_videos(credentials: Credentials) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    youtube = build("youtube", "v3", credentials=credentials)
    channel_response = youtube.channels().list(
        part="snippet,statistics,contentDetails", mine=True
    ).execute()
    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError("No YouTube channel is available for the authorized account")
    channel = channels[0]
    uploads_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids: list[str] = []
    page_token = None
    while True:
        page = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        video_ids.extend(item["contentDetails"]["videoId"] for item in page.get("items", []))
        page_token = page.get("nextPageToken")
        if not page_token or len(video_ids) >= 200:
            break

    videos: list[dict[str, Any]] = []
    for start in range(0, len(video_ids), 50):
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=",".join(video_ids[start : start + 50]),
            maxResults=50,
        ).execute()
        videos.extend(response.get("items", []))
    return channel, videos


def fetch_analytics(credentials: Credentials, days: int = 90) -> dict[str, dict[str, Any]]:
    analytics = build("youtubeAnalytics", "v2", credentials=credentials)
    end_date = datetime.now(timezone.utc).date() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    response = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics=(
            "views,likes,comments,estimatedMinutesWatched,averageViewDuration,"
            "averageViewPercentage,subscribersGained"
        ),
        dimensions="video",
        sort="-views",
        maxResults=200,
    ).execute()
    headers = [header["name"] for header in response.get("columnHeaders", [])]
    return {
        str(row[0]): dict(zip(headers[1:], row[1:]))
        for row in response.get("rows", [])
    }


def create_report(
    channel: dict[str, Any],
    records: list[dict[str, Any]],
    publish_hours: list[int],
    timezone_name: str,
) -> dict[str, Any]:
    stats = channel.get("statistics", {})
    top = records[:10]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": timezone_name,
        "channel": {
            "id": channel.get("id", ""),
            "title": channel.get("snippet", {}).get("title", ""),
            "subscribers": _as_int(stats.get("subscriberCount")),
            "total_views": _as_int(stats.get("viewCount")),
            "video_count": _as_int(stats.get("videoCount")),
        },
        "shorts_analyzed": len(records),
        "recommended_publish_hours": publish_hours,
        "top_shorts": top,
        "all_shorts": records,
    }


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    channel = report["channel"]
    lines = [
        "# YouTube Channel Analysis",
        "",
        f"- Channel: {channel['title']}",
        f"- Subscribers: {channel['subscribers']}",
        f"- Total channel views: {channel['total_views']}",
        f"- Videos: {channel['video_count']}",
        f"- Shorts analyzed: {report['shorts_analyzed']}",
        f"- Timezone: {report['timezone']}",
        "- Recommended daily publish hours: "
        + ", ".join(f"{hour:02d}:00" for hour in report["recommended_publish_hours"]),
        "",
        "## Data Confidence",
        "",
        (
            "- Low: fewer than eight Shorts are available, so upload-time and retention conclusions "
            "are not statistically reliable yet. The four times below are evenly spaced global test slots, not proven winners."
            if report["shorts_analyzed"] < 8
            else "- Moderate: observed upload-hour performance is used, but continue testing before treating it as causal."
        ),
        "- Average viewed percentage can remain unavailable or zero while same-day Analytics data is still processing.",
        "",
        "## Initial 14-Day Strategy",
        "",
        "- Publish four Shorts daily at the listed Europe/Istanbul times, six hours apart.",
        "- Target 35-50 seconds, roughly 80-120 spoken English words, with a hook in the first 1-2 seconds.",
        "- Use 6-10 chronological scenes and concrete search terms; do not publish when visual alignment is below 75/100.",
        "- Favor stock-friendly history: surviving monuments, ancient engineering, archaeology, navigation, inventions, crafts, and visible mysteries.",
        "- Avoid generic modern footage pretending to show a named historical person, battle, rescue, or disaster.",
        "- Rotate hook styles and content pillars, but change only one major variable per slot so results remain interpretable.",
        "- Re-evaluate after at least 30-50 uploads using viewed-vs-swiped-away, average percentage viewed, engagement, shares, and subscribers gained.",
        "",
        "## Top Shorts",
        "",
        "| Title | Views | Avg viewed % | Engagement | Subscribers |",
        "|---|---:|---:|---:|---:|",
    ]
    for record in report["top_shorts"]:
        title = record["title"].replace("|", "\\|")
        lines.append(
            f"| [{title}]({record['url']}) | {record['views']} | "
            f"{record['average_view_percentage']:.1f}% | "
            f"{record['engagement_rate'] * 100:.1f}% | {record['subscribers_gained']} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a YouTube channel and its Shorts")
    parser.add_argument("--authorize-only", action="store_true")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--json-output", default="storage/channel_analysis/latest.json")
    parser.add_argument("--markdown-output", default="CHANNEL_ANALYSIS.md")
    args = parser.parse_args()

    credentials = get_credentials(authorize_only=args.authorize_only)
    if args.authorize_only:
        return
    channel, videos = fetch_channel_and_videos(credentials)
    analytics = fetch_analytics(credentials, days=args.days)
    records = build_video_records(videos, analytics, timezone_name=args.timezone)
    hours = recommend_publish_hours(records, count=4)
    report = create_report(channel, records, hours, args.timezone)

    json_output = ROOT / args.json_output
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output = ROOT / args.markdown_output
    write_markdown_report(report, markdown_output)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
