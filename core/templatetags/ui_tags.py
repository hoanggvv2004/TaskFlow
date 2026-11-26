from django import template

register = template.Library()


@register.inclusion_tag("components/avatar.html")
def user_avatar(user, size="32"):
    return {"user": user, "size": size}


@register.filter
def badge_class(slug):
    mapping = {
        "low": "badge-low",
        "medium": "badge-medium",
        "high": "badge-high",
        "urgent": "badge-urgent",
        "planning": "badge-muted",
        "active": "badge-info",
        "on-hold": "badge-medium",
        "completed": "badge-success",
        "cancelled": "badge-danger",
        "todo": "badge-muted",
        "in-progress": "badge-info",
        "review": "badge-medium",
        "blocked": "badge-danger",
        "delayed": "badge-danger",
        "paused": "badge-medium",
        "rework": "badge-high",
        "rejected": "badge-danger",
    }
    return mapping.get(slug, "badge-muted")


@register.filter
def workload_class(label):
    return {
        "Light": "wl-light",
        "Normal": "wl-normal",
        "High": "wl-high",
        "Overloaded": "wl-over",
    }.get(label, "wl-normal")


@register.filter
def notif_icon(ntype):
    return {
        "TASK_ASSIGNED": "bi-person-check",
        "TASK_UPDATED": "bi-arrow-repeat",
        "TASK_COMMENT": "bi-chat-dots",
        "DEADLINE_CHANGED": "bi-calendar-event",
        "TASK_DUE_SOON": "bi-alarm",
        "TASK_OVERDUE": "bi-exclamation-triangle",
        "PROJECT_MEMBER_ADDED": "bi-people",
        "PROJECT_UPDATED": "bi-folder2",
        "TASK_COMPLETED": "bi-check2-circle",
    }.get(ntype, "bi-bell")


@register.filter
def notif_tone(ntype):
    return {
        "TASK_ASSIGNED": "tone-primary",
        "TASK_UPDATED": "tone-info",
        "TASK_COMMENT": "tone-violet",
        "DEADLINE_CHANGED": "tone-warning",
        "TASK_DUE_SOON": "tone-warning",
        "TASK_OVERDUE": "tone-danger",
        "PROJECT_MEMBER_ADDED": "tone-success",
        "PROJECT_UPDATED": "tone-muted",
        "TASK_COMPLETED": "tone-success",
    }.get(ntype, "tone-muted")


@register.filter
def activity_icon(action):
    return {
        "project_created": "bi-folder-plus",
        "project_updated": "bi-folder2",
        "member_added": "bi-person-plus",
        "member_removed": "bi-person-dash",
        "member_role_changed": "bi-shield-check",
        "owner_transferred": "bi-arrow-left-right",
        "task_created": "bi-plus-square",
        "task_assigned": "bi-person-check",
        "task_status_changed": "bi-arrow-repeat",
        "deadline_changed": "bi-calendar-event",
        "task_commented": "bi-chat-dots",
        "document_uploaded": "bi-paperclip",
    }.get(action, "bi-activity")


@register.filter
def progress_tone(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return ""
    if value >= 80:
        return "success"
    if value >= 40:
        return ""
    return "warning"


@register.filter
def percent(part, whole):
    try:
        part = float(part)
        whole = float(whole)
    except (TypeError, ValueError):
        return 0
    if not whole:
        return 0
    return int(round(part / whole * 100))


@register.simple_tag(takes_context=True)
def querystring_without(context, *keys):
    request = context.get("request")
    if not request:
        return ""
    params = request.GET.copy()
    for key in keys:
        params.pop(key, None)
    encoded = params.urlencode()
    return encoded
