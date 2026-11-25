from notifications.models import Notification


def notify(user, ntype, title, message, url=""):
    if not user:
        return None
    if hasattr(user, "email_notification") and not user.email_notification and not user.browser_notification:
        return None
    return Notification.objects.create(
        user=user,
        type=ntype,
        title=title,
        message=message,
        url=url or "",
    )


def notify_users(users, ntype, title, message, url="", exclude_user=None):
    created = []
    seen = set()
    for user in users:
        if not user or user.pk in seen:
            continue
        if exclude_user and user.pk == exclude_user.pk:
            continue
        seen.add(user.pk)
        item = notify(user, ntype, title, message, url)
        if item:
            created.append(item)
    return created


def mark_due_notifications(tasks, ntype, title_tpl, message_tpl):
    for task in tasks:
        assignees = task.assignees.all()
        url = task.get_absolute_url()
        for user in assignees:
            exists = Notification.objects.filter(
                user=user,
                type=ntype,
                url=url,
                is_read=False,
            ).exists()
            if exists:
                continue
            notify(
                user,
                ntype,
                title_tpl.format(code=task.code),
                message_tpl.format(code=task.code, title=task.title),
                url,
            )
