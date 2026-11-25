from django.urls import path

from tasks import views

app_name = "tasks"

urlpatterns = [
    path("", views.task_list, name="list"),
    path("mine/", views.my_tasks, name="mine"),
    path("create/", views.task_create, name="create"),
    path("quick-create/", views.quick_create_task, name="quick_create"),
    path("kanban/", views.global_kanban, name="kanban"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/events/", views.calendar_events, name="calendar_events"),
    path("documents/", views.document_list, name="documents"),
    path("documents/<int:document_id>/download/", views.document_download, name="document_download"),
    path("documents/<int:document_id>/delete/", views.document_delete, name="document_delete"),
    path("<int:task_id>/", views.task_detail, name="detail"),
    path("<int:task_id>/edit/", views.task_edit, name="edit"),
    path("<int:task_id>/delete/", views.task_delete, name="delete"),
    path("<int:task_id>/status/", views.ajax_status, name="ajax_status"),
    path("<int:task_id>/comments/", views.ajax_comment_add, name="ajax_comment_add"),
    path("<int:task_id>/checklist/", views.ajax_checklist_add, name="ajax_checklist_add"),
    path("<int:task_id>/attachments/", views.ajax_document_upload, name="ajax_document_upload"),
    path("comments/<int:comment_id>/edit/", views.ajax_comment_edit, name="ajax_comment_edit"),
    path("comments/<int:comment_id>/delete/", views.ajax_comment_delete, name="ajax_comment_delete"),
    path("checklist/<int:item_id>/toggle/", views.ajax_checklist_toggle, name="ajax_checklist_toggle"),
    path("checklist/<int:item_id>/delete/", views.ajax_checklist_delete, name="ajax_checklist_delete"),
]
