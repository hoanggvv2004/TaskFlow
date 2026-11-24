from django.urls import path

from projects import views
from reports.views import reports_home
from tasks.configuration_views import project_workflow
from tasks.import_views import project_task_import, project_task_template

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("create/", views.project_create, name="create"),
    path("<int:project_id>/", views.project_detail, name="detail"),
    path("<int:project_id>/edit/", views.project_edit, name="edit"),
    path("<int:project_id>/archive/", views.project_lifecycle, {"action": "archive"}, name="archive"),
    path("<int:project_id>/restore/", views.project_lifecycle, {"action": "restore"}, name="restore"),
    path("<int:project_id>/delete/", views.project_lifecycle, {"action": "delete"}, name="delete"),
    path("<int:project_id>/tasks/", views.project_tasks, name="tasks"),
    path("<int:project_id>/tasks/import/", project_task_import, name="task_import"),
    path("<int:project_id>/tasks/template/", project_task_template, name="task_template"),
    path("<int:project_id>/kanban/", views.project_kanban, name="kanban"),
    path("<int:project_id>/members/", views.project_members, name="members"),
    path("<int:project_id>/members/add/", views.member_add, name="member_add"),
    path("<int:project_id>/members/<int:member_id>/remove/", views.member_remove, name="member_remove"),
    path("<int:project_id>/members/<int:member_id>/role/", views.member_role, name="member_role"),
    path("<int:project_id>/documents/", views.project_documents, name="documents"),
    path("<int:project_id>/activity/", views.project_activity, name="activity"),
    path("<int:project_id>/reports/", reports_home, name="reports"),
    path("<int:project_id>/settings/", views.project_settings, name="settings"),
    path("<int:project_id>/workflow/", project_workflow, name="workflow"),
    path("<int:project_id>/transfer-owner/", views.project_transfer_owner, name="transfer_owner"),
]
