"""Shared period-bucketing helpers for dashboard/report endpoints across the warehouse and
retail portals. Frontend period vocabulary is always one of '24h' | 'weekly' | 'monthly' |
'yearly' (see warehouse's TimePeriodSelect.jsx and retail's period <select>s) - there is no
'daily'. Any unrecognized value falls back to 'monthly'.
"""
from datetime import datetime, timedelta, timezone

_WINDOW = {
    "24h": timedelta(hours=24),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "yearly": timedelta(days=365),
}

# (bucket_count, bucket_width, label_format) per period - chosen so charts get a readable
# number of points: hourly over a day, daily over a week/month, monthly over a year.
_BUCKETS = {
    "24h": (24, timedelta(hours=1), "%H:00"),
    "weekly": (7, timedelta(days=1), "%d %b"),
    "monthly": (30, timedelta(days=1), "%d %b"),
    "yearly": (12, timedelta(days=30), "%b %Y"),
}


def period_start(period: str, end: datetime | None = None) -> datetime:
    end = end or datetime.now(timezone.utc)
    return end - _WINDOW.get(period, _WINDOW["monthly"])


def build_buckets(period: str, end: datetime | None = None) -> list[tuple[datetime, datetime, str]]:
    """Returns [(bucket_start, bucket_end, label), ...] oldest-first, covering the requested
    window ending at `end` (defaults to now)."""
    end = end or datetime.now(timezone.utc)
    count, width, fmt = _BUCKETS.get(period, _BUCKETS["monthly"])
    buckets = []
    for i in range(count - 1, -1, -1):
        b_end = end - width * i
        b_start = b_end - width
        buckets.append((b_start, b_end, b_end.strftime(fmt)))
    return buckets
