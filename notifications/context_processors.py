from notifications.models import Notification


def notification_context(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0, "header_notifications": []}
    qs = Notification.objects.filter(user=request.user)
    return {
        "unread_notification_count": qs.filter(is_read=False).count(),
        "header_notifications": qs[:8],
    }
