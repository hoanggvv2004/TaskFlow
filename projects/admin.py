from django.contrib import admin

from core.admin import ReadOnlyAdmin
from projects.models import Project, ProjectMember, ProjectPriority, ProjectStatus


class ProjectStatusInline(admin.TabularInline):
    model = ProjectStatus
    extra = 0
    fields = ("status", "is_current", "changed_at", "changed_by")
    readonly_fields = ("status", "is_current", "changed_at", "changed_by")
    can_delete = False


class ProjectPriorityInline(admin.TabularInline):
    model = ProjectPriority
    extra = 0
    fields = ("priority", "is_current", "changed_at", "changed_by")
    readonly_fields = ("priority", "is_current", "changed_at", "changed_by")
    can_delete = False


@admin.register(Project)
class ProjectAdmin(ReadOnlyAdmin):
    list_display = ("code", "name", "owner", "end_date", "archived_at", "is_deleted")
    list_filter = ("archived_at", "is_deleted")
    search_fields = ("code", "name")
    inlines = (ProjectStatusInline, ProjectPriorityInline)


@admin.register(ProjectMember)
class ProjectMemberAdmin(ReadOnlyAdmin):
    list_display = ("project", "user", "role", "joined_at")
    list_filter = ("role",)
