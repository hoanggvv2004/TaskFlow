from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from activity.models import ActivityLog
from core.permissions import is_admin


@login_required
def activity_list(request):
    logs = ActivityLog.objects.select_related("user", "project", "task")
    if not is_admin(request.user):
        logs = logs.filter(project__members__user=request.user).distinct()
    page = Paginator(logs, 20).get_page(request.GET.get("page"))
    return render(request, "activity/list.html", {"page": page})
