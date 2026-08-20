"""Shared date-range resolution for report export endpoints.

`resolve_report_date_range` backs the older single-date/date-range activity exports (Super
Admin's Activities export, Support ticket export) — every portal there accepts exactly `date`
OR (`date_from` AND `date_to`), never a mix.

`resolve_week_or_month_range` backs the newer Vendor/Warehouse/Retail dashboard "Export Report"
dialog, which only ever offers two choices relative to one selected date: the calendar week
(Monday through the selected date) or the calendar month (the 1st through the selected date)."""
from datetime import date, timedelta

from app.core.exceptions import BadRequestException


def resolve_report_date_range(
    date_: date | None, date_from: date | None, date_to: date | None
) -> tuple[date, date, str]:
    if date_ is not None:
        if date_from is not None or date_to is not None:
            raise BadRequestException("Provide either 'date' or 'date_from'+'date_to', not both")
        return date_, date_, f"Report Date: {date_.strftime('%d %b %Y')}"

    if date_from is not None and date_to is not None:
        if date_from > date_to:
            raise BadRequestException("'date_from' must be on or before 'date_to'")
        return date_from, date_to, f"Report Period: {date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}"

    raise BadRequestException("Provide either 'date' or both 'date_from' and 'date_to'")


def resolve_week_or_month_range(mode: str, selected_date: date) -> tuple[date, date, str]:
    """`mode="week"` -> the Monday of `selected_date`'s calendar week through `selected_date`
    itself (a Monday selection covers just that Monday). `mode="month"` -> the 1st of
    `selected_date`'s month through `selected_date` itself."""
    if mode == "week":
        start = selected_date - timedelta(days=selected_date.weekday())
        label = f"Week of {start.strftime('%d %b %Y')} to {selected_date.strftime('%d %b %Y')}"
        return start, selected_date, label

    if mode == "month":
        start = selected_date.replace(day=1)
        label = f"Month of {start.strftime('%d %b %Y')} to {selected_date.strftime('%d %b %Y')}"
        return start, selected_date, label

    raise BadRequestException("'mode' must be 'week' or 'month'")
