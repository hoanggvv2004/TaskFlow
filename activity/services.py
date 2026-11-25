from activity.models import ActivityLog


def log_activity(user, action, description, project=None, task=None, old_value="", new_value=""):
    return ActivityLog.objects.create(
        user=user,
        project=project,
        task=task,
        action=action,
        description=description,
        old_value=old_value or "",
        new_value=new_value or "",
    )
