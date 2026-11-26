import json
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from activity.models import ActivityLog
from core.permissions import is_admin
from core.utils import workload_label
from projects.models import Project
from tasks.models import Task


def visible_projects(user):
    projects = Project.objects.with_current().filter(archived_at__isnull=True).select_related("owner")
    if is_admin(user):
        return projects
    return projects.filter(members__user=user).distinct()


def visible_tasks(user):
    tasks = Task.objects.with_current().filter(project__archived_at__isnull=True).select_related(
        "project"
    ).prefetch_related("assignees")
    if is_admin(user):
        return tasks
    return tasks.filter(project__members__user=user).distinct()


def count_by_status(tasks):
    data = Counter()
    for task in tasks:
        data[task.status.stage] += 1
    return data


def count_by_priority(tasks):
    data = Counter()
    for task in tasks:
        data[task.priority.slug] += 1
    return data


def completed_by_month(tasks, months=6):
    today = timezone.localdate()
    buckets = []
    for i in range(months - 1, -1, -1):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        label = f"{month:02d}/{year}"
        buckets.append((year, month, label, 0))
    indexed = {(y, m): idx for idx, (y, m, _, __) in enumerate(buckets)}
    for task in tasks:
        if not task.is_completed:
            continue
        dt = timezone.localtime(task.updated_at).date()
        key = (dt.year, dt.month)
        if key in indexed:
            y, m, label, value = buckets[indexed[key]]
            buckets[indexed[key]] = (y, m, label, value + 1)
    return [{"label": item[2], "value": item[3]} for item in buckets]


def completed_by_week(tasks, weeks=8):
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday())
    buckets = []
    for i in range(weeks - 1, -1, -1):
        week_start = start - timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        buckets.append((week_start, week_end, f"{week_start.strftime('%d/%m')}", 0))
    for task in tasks:
        if not task.is_completed:
            continue
        dt = timezone.localtime(task.updated_at).date()
        for idx, (ws, we, label, value) in enumerate(buckets):
            if ws <= dt <= we:
                buckets[idx] = (ws, we, label, value + 1)
                break
    return [{"label": item[2], "value": item[3]} for item in buckets]


def workload_rows(projects):
    rows = []
    members = {}
    for project in projects.prefetch_related("members__user"):
        for membership in project.members.all():
            members[membership.user_id] = membership.user
    tasks = Task.objects.open_tasks().filter(project__in=projects).prefetch_related("assignees")
    counts = Counter()
    hours = defaultdict(float)
    for task in tasks:
        for user in task.assignees.all():
            counts[user.id] += 1
            hours[user.id] += float(task.estimated_hours or 0)
    for user_id, user in members.items():
        active = counts.get(user_id, 0)
        rows.append(
            {
                "user": user,
                "active": active,
                "hours": hours.get(user_id, 0),
                "label": workload_label(active),
            }
        )
    rows.sort(key=lambda item: item["active"], reverse=True)
    return rows


def admin_metrics():
    users = User.objects.all()
    projects = Project.objects.with_current().filter(archived_at__isnull=True)
    tasks = list(Task.objects.with_current().filter(project__in=projects).select_related("project"))
    status = count_by_status(tasks)
    month_ago = timezone.now() - timedelta(days=30)
    return {
        "total_users": users.count(),
        "total_projects": projects.count(),
        "total_tasks": len(tasks),
        "active_projects": projects.filter(current_status_slug="active").count(),
        "completed_projects": projects.filter(current_status_slug="completed").count(),
        "todo": status.get("todo", 0),
        "in_progress": status.get("in-progress", 0),
        "review": status.get("review", 0),
        "completed": status.get("completed", 0),
        "overdue": sum(1 for t in tasks if t.is_overdue),
        "new_users": users.filter(date_joined__gte=month_ago).count(),
        "recent_activity": ActivityLog.objects.select_related("user", "project")[:12],
        "project_status_chart": json.dumps(list(projects.values("current_status_name").annotate(total=Count("id")))),
        "task_status_chart": json.dumps(status),
        "task_priority_chart": json.dumps(count_by_priority(tasks)),
        "completed_month": json.dumps(completed_by_month(tasks)),
        "top_members": User.objects.annotate(task_total=Count("task_assignments", filter=Q(
            task_assignments__task__project__in=projects, task_assignments__task__is_deleted=False,
        ))).order_by("-task_total")[:6],
        "top_projects": projects.annotate(
            task_total=Count("tasks", filter=Q(tasks__is_deleted=False))
        ).order_by("-task_total")[:6],
    }
