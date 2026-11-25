from django.contrib import admin

from activity.models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "project", "task")
    list_filter = ("action",)
    search_fields = ("description",)
    readonly_fields = ("user", "project", "task", "action", "description", "old_value", "new_value", "created_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
