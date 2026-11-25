from django.contrib import admin

from core.admin import ReadOnlyAdmin
from core.models import Priority, Status
from tasks.models import (
    Document,
    Task,
    TaskAssignment,
    TaskChecklist,
    TaskComment,
    TaskHistory,
    TaskPriority,
    TaskStatus,
)


if not admin.site.is_registered(Status):
    admin.site.register(
        Status,
        list_display=("name", "slug", "scope", "sort_order"),
        list_filter=("scope",),
    )

if not admin.site.is_registered(Priority):
    admin.site.register(
        Priority,
        list_display=("name", "slug", "scope", "sort_order"),
        list_filter=("scope",),
    )


class TaskStatusInline(admin.TabularInline):
    model = TaskStatus
    extra = 0
    fields = ("status", "is_current", "changed_at", "changed_by")
    readonly_fields = ("status", "is_current", "changed_at", "changed_by")
    can_delete = False


class TaskPriorityInline(admin.TabularInline):
    model = TaskPriority
    extra = 0
    fields = ("priority", "is_current", "changed_at", "changed_by")
    readonly_fields = ("priority", "is_current", "changed_at", "changed_by")
    can_delete = False


@admin.register(Task)
class TaskAdmin(ReadOnlyAdmin):
    list_display = ("code", "title", "project", "due_date", "progress", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("code", "title")
    inlines = (TaskStatusInline, TaskPriorityInline)


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(ReadOnlyAdmin):
    list_display = ("task", "user", "assigned_at")


@admin.register(TaskComment)
class TaskCommentAdmin(ReadOnlyAdmin):
    list_display = ("task", "user", "created_at")


@admin.register(TaskChecklist)
class TaskChecklistAdmin(ReadOnlyAdmin):
    list_display = ("task", "title", "is_completed")


@admin.register(TaskHistory)
class TaskHistoryAdmin(ReadOnlyAdmin):
    list_display = ("task", "old_status", "new_status", "user", "created_at")


@admin.register(Document)
class DocumentAdmin(ReadOnlyAdmin):
    list_display = ("original_name", "project", "task", "uploaded_by", "created_at", "is_deleted")
