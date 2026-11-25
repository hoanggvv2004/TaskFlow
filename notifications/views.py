from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from notifications.models import Notification


@login_required
def notification_list(request):
    qs = Notification.objects.filter(user=request.user)
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {"page": page})


@login_required
@require_POST
def mark_read(request, notification_id):
    item = get_object_or_404(Notification, pk=notification_id, user=request.user)
    item.is_read = True
    item.save(update_fields=["is_read"])
    unread = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({"success": True, "unread": unread})


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"success": True, "unread": 0, "message": "Đã đánh dấu tất cả là đã đọc."})


@login_required
def header_feed(request):
    items = Notification.objects.filter(user=request.user)[:8]
    unread = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse(
        {
            "success": True,
            "unread": unread,
            "items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "message": item.message,
                    "url": item.url,
                    "is_read": item.is_read,
                    "created_at": item.created_at.strftime("%d/%m %H:%M"),
                }
                for item in items
            ],
        }
    )
