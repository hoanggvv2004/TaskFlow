from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        TASK_ASSIGNED = "TASK_ASSIGNED", "Task assigned"
        TASK_UPDATED = "TASK_UPDATED", "Task updated"
        TASK_COMMENT = "TASK_COMMENT", "Task comment"
        DEADLINE_CHANGED = "DEADLINE_CHANGED", "Deadline changed"
        TASK_DUE_SOON = "TASK_DUE_SOON", "Task due soon"
        TASK_OVERDUE = "TASK_OVERDUE", "Task overdue"
        PROJECT_MEMBER_ADDED = "PROJECT_MEMBER_ADDED", "Added to project"
        PROJECT_UPDATED = "PROJECT_UPDATED", "Project updated"
        TASK_COMPLETED = "TASK_COMPLETED", "Task completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=40, choices=Type.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return self.title
