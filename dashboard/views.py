import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone

from activity.models import ActivityLog
from core.permissions import can_create_project, can_view_own_department, is_admin, is_department_head
from dashboard.services import admin_metrics, count_by_priority, count_by_status, completed_by_week, visible_projects, visible_tasks, workload_rows
from projects.models import ProjectMember


@login_required
def home(request):
    if is_admin(request.user):
        return render(request, "dashboard/admin.html", {"metrics": admin_metrics()})

    projects = visible_projects(request.user)
    all_visible_tasks = visible_tasks(request.user)
    managed = projects.filter(members__user=request.user, members__role__in=[ProjectMember.Role.OWNER, ProjectMember.Role.MANAGER])
    has_department_view = can_view_own_department(request.user)
    is_manager = has_department_view or managed.exists()
    if is_manager:
        projects = managed
    tasks = list(all_visible_tasks.filter(project__in=projects))
    my_tasks = list(all_visible_tasks.filter(assignments__user=request.user))
    workload = workload_rows(projects)[:8] if is_manager else []
    today = timezone.localdate()
    status = count_by_status(tasks)
    my_status = count_by_status(my_tasks)
    context = {
        "projects": projects,
        "tasks": tasks,
        "my_tasks": my_tasks,
        "today_tasks": [t for t in my_tasks if t.due_date == today and not t.status.is_closed],
        "due_soon": [t for t in my_tasks if t.is_due_soon],
        "overdue": [t for t in my_tasks if t.is_overdue],
        "completed": [t for t in my_tasks if t.is_completed],
        "upcoming": sorted(
            [t for t in my_tasks if t.due_date and not t.status.is_closed],
            key=lambda item: item.due_date,
        )[:6],
        "stats": {
            "total_projects": projects.count(),
            "active_projects": projects.with_current().filter(current_status_slug="active").count(),
            "total_tasks": len(tasks),
            "completed_tasks": status.get("completed", 0),
            "in_progress": status.get("in-progress", 0),
            "overdue": sum(1 for t in tasks if t.is_overdue),
            "my_projects": projects.count(),
            "my_tasks": len(my_tasks),
            "my_today": sum(1 for t in my_tasks if t.due_date == today and not t.status.is_closed),
            "my_due_soon": sum(1 for t in my_tasks if t.is_due_soon),
            "my_overdue": sum(1 for t in my_tasks if t.is_overdue),
            "my_completed": my_status.get("completed", 0),
        },
        "status_chart": status,
        "priority_chart": count_by_priority(tasks),
        "completed_week": completed_by_week(tasks),
        "project_progress": [
            {"project": p, "progress": p.progress(), "stats": p.task_stats()} for p in projects[:6]
        ],
        "workload": workload,
        "recent_activity": ActivityLog.objects.filter(project__in=projects).select_related("user", "project", "task")[:10],
        "is_manager": is_manager,
        "is_department_head": has_department_view and is_department_head(request.user),
        "can_create_project": can_create_project(request.user),
        "status_chart_json": json.dumps(status),
        "priority_chart_json": json.dumps(count_by_priority(tasks)),
        "completed_week_json": json.dumps(completed_by_week(tasks)),
        "progress_chart_json": json.dumps(
            [{"label": p.name, "value": p.progress()} for p in projects[:6]]
        ),
        "workload_json": json.dumps(
            [{"label": row["user"].get_display_name(), "value": row["active"]} for row in workload]
        ),
    }
    template = "dashboard/manager.html" if context["is_manager"] else "dashboard/member.html"
    return render(request, template, context)


@login_required
def system_activity(request):
    if not is_admin(request.user):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Chỉ Admin mới xem được nhật ký hệ thống.")
    logs = ActivityLog.objects.select_related("user", "project", "task")
    page = Paginator(logs, 20).get_page(request.GET.get("page"))
    return render(request, "activity/system.html", {"page": page})
