from datetime import date

from django.utils import timezone


def days_remaining(end_date):
    if not end_date:
        return None
    today = timezone.localdate()
    return (end_date - today).days


def is_due_soon(due_date, days=3):
    if not due_date:
        return False
    remaining = (due_date - timezone.localdate()).days
    return 0 <= remaining <= days


def is_overdue(due_date, is_completed=False):
    if not due_date or is_completed:
        return False
    return timezone.localdate() > due_date


def workload_label(active_count):
    if active_count <= 3:
        return "Light"
    if active_count <= 6:
        return "Normal"
    if active_count <= 9:
        return "High"
    return "Overloaded"


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def month_start(dt=None):
    current = dt or timezone.localdate()
    return date(current.year, current.month, 1)
