from django.urls import path

from activity import views

app_name = "activity"

urlpatterns = [
    path("", views.activity_list, name="list"),
]
