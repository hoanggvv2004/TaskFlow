from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render

from accounts.models import User
from core.permissions import is_admin
from projects.models import Project
from tasks.models import Task


def handler403_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


def handler404_view(request, exception=None):
    return render(request, "errors/404.html", status=404)


def handler500_view(request):
    return render(request, "errors/500.html", status=500)


def _search_queryset(user, query):
    projects = Project.objects.none()
    tasks = Task.objects.none()
    users = User.objects.none()
    if not query:
        return projects, tasks, users

    project_filter = Q(name__icontains=query) | Q(code__icontains=query) | Q(description__icontains=query)
    if is_admin(user):
        projects = Project.objects.with_current().filter(project_filter).select_related("owner")
        tasks = Task.objects.filter(
            Q(title__icontains=query) | Q(code__icontains=query) | Q(description__icontains=query)
        ).with_current().select_related("project")
        users = User.objects.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    else:
        projects = (
            Project.objects.filter(members__user=user)
            .filter(project_filter)
            .with_current()
            .select_related("owner")
            .distinct()
        )
        tasks = (
            Task.objects.filter(project__members__user=user)
            .filter(Q(title__icontains=query) | Q(code__icontains=query) | Q(description__icontains=query))
            .with_current()
            .select_related("project")
            .distinct()
        )
        users = User.objects.filter(
            Q(project_memberships__project__members__user=user)
            | Q(pk=user.pk)
        ).filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        ).distinct()
    return projects[:8], tasks[:8], users[:8]


@login_required
def global_search(request):
    query = (request.GET.get("q") or "").strip()
    projects, tasks, users = _search_queryset(request.user, query)
    return render(
        request,
        "core/search.html",
        {
            "query": query,
            "projects": projects,
            "tasks": tasks,
            "users": users,
        },
    )


@login_required
def search_api(request):
    query = (request.GET.get("q") or "").strip()
    projects, tasks, users = _search_queryset(request.user, query)
    return JsonResponse(
        {
            "success": True,
            "projects": [
                {"id": p.id, "name": p.name, "code": p.code, "url": p.get_absolute_url()}
                for p in projects
            ],
            "tasks": [
                {"id": t.id, "name": t.title, "code": t.code, "url": t.get_absolute_url()}
                for t in tasks
            ],
            "members": [
                {
                    "id": u.id,
                    "name": u.get_display_name(),
                    "email": u.email,
                    "url": u.get_absolute_url(),
                }
                for u in users
            ],
        }
    )
