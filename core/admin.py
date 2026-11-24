from django.contrib import admin

from core.models import Priority, Status


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "scope", "sort_order")
    list_filter = ("scope",)


@admin.register(Priority)
class PriorityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "scope", "sort_order")
    list_filter = ("scope",)
