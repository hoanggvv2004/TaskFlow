from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("overview/", views.home, name="overview"),
    path("system-activity/", views.system_activity, name="system_activity"),
]
