from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.global_search, name="search"),
    path("api/search/", views.search_api, name="search_api"),
]
