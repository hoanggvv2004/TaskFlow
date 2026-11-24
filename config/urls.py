from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import handler403_view, handler404_view, handler500_view

admin.site.site_header = "TaskFlow Django Admin"
admin.site.site_title = "TaskFlow"
admin.site.index_title = "Database explorer"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("projects/", include("projects.urls")),
    path("tasks/", include("tasks.urls")),
    path("notifications/", include("notifications.urls")),
    path("activity/", include("activity.urls")),
    path("reports/", include("reports.urls")),
    path("search/", include("core.urls")),
]

handler403 = handler403_view
handler404 = handler404_view
handler500 = handler500_view

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
