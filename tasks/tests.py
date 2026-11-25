from datetime import date, timedelta
from io import BytesIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from accounts.models import User
from core.models import Priority, Status
from projects.models import ProjectMember
from projects.services import add_project_member, create_project
from tasks.forms import TaskForm
from tasks.models import (
    Task,
    TaskChecklist,
    TaskComment,
    TaskImport,
    TaskPriority,
    TaskStatus,
    TaskTransition,
    TaskType,
)
from tasks.services import add_comment, assign_users, create_task, update_task_status
from tasks.workflow import save_configuration


def seed():
    Status.objects.get_or_create(scope="PROJECT", slug="active", defaults={"name": "Active", "sort_order": 1})
    Priority.objects.get_or_create(scope="PROJECT", slug="medium", defaults={"name": "Medium", "sort_order": 2})
    stage_map = {
        "todo": Status.Stage.TODO,
        "in-progress": Status.Stage.ACTIVE,
        "rework": Status.Stage.REWORK,
        "review": Status.Stage.REVIEW,
        "completed": Status.Stage.COMPLETED,
    }
    for slug, name, order in [
        ("todo", "To-do", 1),
        ("in-progress", "In Progress", 2),
        ("review", "Review", 3),
        ("completed", "Completed", 4),
        ("rework", "Rework", 5),
    ]:
        Status.objects.update_or_create(
            scope="TASK",
            slug=slug,
            defaults={"name": name, "sort_order": order, "stage": stage_map[slug]},
        )
    Priority.objects.get_or_create(scope="TASK", slug="high", defaults={"name": "High", "sort_order": 3})
    Priority.objects.get_or_create(scope="TASK", slug="medium", defaults={"name": "Medium", "sort_order": 2})


class TaskWorkflowTests(TestCase):
    def setUp(self):
        seed()
        self.manager = User.objects.create_user(
            "manager", "manager@test.local", "Manager@123", role=User.Role.PROJECT_MANAGER, first_name="Lan"
        )
        self.member = User.objects.create_user("member", "member@test.local", "Member@123", role=User.Role.MEMBER, first_name="Bao")
        self.outsider = User.objects.create_user("out", "out@test.local", "Member@123", role=User.Role.MEMBER, first_name="Out")
        self.project = create_project(
            self.manager,
            {
                "name": "Customer CRM System",
                "description": "CRM",
                "category": "Internal",
                "start_date": date.today() - timedelta(days=5),
                "end_date": date.today() + timedelta(days=20),
                "status": Status.objects.get(scope="PROJECT", slug="active"),
                "priority": Priority.objects.get(scope="PROJECT", slug="medium"),
            },
        )
        add_project_member(self.project, self.member, ProjectMember.Role.MEMBER, self.manager)
        self.todo = Status.objects.get(scope="TASK", slug="todo")
        self.doing = Status.objects.get(scope="TASK", slug="in-progress")
        self.review = Status.objects.get(scope="TASK", slug="review")
        self.done = Status.objects.get(scope="TASK", slug="completed")
        self.priority = Priority.objects.get(scope="TASK", slug="high")
        self.task = create_task(
            self.manager,
            self.project,
            {
                "title": "Xây dựng đăng nhập",
                "description": "Auth",
                "status": self.todo,
                "priority": self.priority,
                "start_date": date.today(),
                "due_date": date.today() + timedelta(days=5),
                "estimated_hours": 8,
                "actual_hours": 0,
                "progress": 0,
            },
            [self.member.id],
        )

    def test_create_and_assign_task(self):
        self.assertTrue(self.task.code.startswith("TASK-"))
        self.assertTrue(self.task.assignments.filter(user=self.member).exists())

    def test_task_create_view_sets_initial_status_and_priority(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("tasks:create") + "?project=%d" % self.project.pk,
            {
                "title": "Tạo qua form",
                "description": "Kiểm thử tạo task",
                "priority": self.priority.pk,
                "start_date": date.today().isoformat(),
                "due_date": (date.today() + timedelta(days=3)).isoformat(),
                "estimated_hours": "2",
                "actual_hours": "0",
                "progress": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title="Tạo qua form")
        self.assertTrue(TaskStatus.objects.filter(task=task, status=self.todo, is_current=True).exists())
        self.assertTrue(TaskPriority.objects.filter(task=task, priority=self.priority, is_current=True).exists())

    def test_task_form_is_valid_for_new_instance(self):
        form = TaskForm(
            data={
                "title": "Task mới",
                "description": "",
                "priority": self.priority.pk,
                "start_date": date.today().isoformat(),
                "due_date": (date.today() + timedelta(days=3)).isoformat(),
                "estimated_hours": "1",
                "actual_hours": "0",
                "progress": "0",
            },
            project=self.project,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_cannot_assign_outsider(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            assign_users(self.task, [self.outsider.id], self.manager)

    def test_due_date_outside_project_requires_confirm(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            create_task(
                self.manager,
                self.project,
                {
                    "title": "Late task",
                    "description": "",
                    "status": self.todo,
                    "priority": self.priority,
                    "due_date": self.project.end_date + timedelta(days=3),
                    "progress": 0,
                },
            )

    def test_update_status_and_progress_rules(self):
        update_task_status(self.task, self.doing, self.member)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status.slug, "in-progress")
        with self.assertRaises(ValidationError):
            update_task_status(self.task, self.done, self.manager)
        update_task_status(self.task, self.review, self.member)
        with self.assertRaises(ValidationError):
            update_task_status(self.task, self.done, self.member)
        update_task_status(self.task, self.done, self.manager)
        self.task.refresh_from_db()
        self.assertEqual(self.task.progress, 100)
        update_task_status(self.task, Status.objects.get(scope="TASK", slug="rework"), self.manager, "Bổ sung ví dụ")
        self.task.refresh_from_db()
        self.assertLess(self.task.progress, 100)
        self.assertEqual(self.task.history.first().note, "Bổ sung ví dụ")

    def test_unassigned_member_cannot_move_task(self):
        add_project_member(self.project, self.outsider, ProjectMember.Role.MEMBER, self.manager)
        with self.assertRaises(PermissionDenied):
            update_task_status(self.task, self.doing, self.outsider)

    def test_form_edit_does_not_set_status(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("tasks:edit", args=[self.task.pk]), {
            "title": "Tên mới", "priority": self.priority.pk, "status": self.done.pk,
            "estimated_hours": "8", "actual_hours": "0", "progress": "40",
        })
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, self.todo)
        self.assertEqual(self.task.title, "Tên mới")

    def test_workflow_configuration_from_project_settings(self):
        self.client.force_login(self.manager)
        url = reverse("projects:workflow", args=[self.project.pk])
        self.assertContains(self.client.get(url), "Lưu luồng công việc")
        self.client.post(url, {"action": "status", "name": "Đang thiết kế", "color": "#2359ff",
                               "stage": Status.Stage.ACTIVE, "sort_order": 10})
        custom = self.project.custom_task_statuses.get(name="Đang thiết kế")
        response = self.client.post(url, {
            "action": "workflow", "statuses": [self.todo.pk, custom.pk], "initial": self.todo.pk,
            "form-TOTAL_FORMS": 1, "form-INITIAL_FORMS": 0,
            "form-0-source": self.todo.pk, "form-0-target": custom.pk, "form-0-role": TaskTransition.Role.ASSIGNEE,
        })
        self.assertEqual(response.status_code, 302)
        with self.assertRaises(ValidationError):
            update_task_status(self.task, self.doing, self.member)
        update_task_status(self.task, custom, self.member)
        self.assertContains(self.client.get(reverse("projects:kanban", args=[self.project.pk])), "Đang thiết kế")
        with self.assertRaises(ValidationError):
            save_configuration(self.project, self.manager, self.todo, [self.todo], [])

    def test_excel_template_import_and_retry(self):
        self.client.force_login(self.manager)
        task_type = TaskType.objects.create(project=self.project, name="Kiểm thử")
        response = self.client.get(reverse("projects:task_template", args=[self.project.pk]))
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook["Gia tri du an"]["B2"].value, task_type.name)
        workbook["Tasks"].append(("Review đăng nhập", "Đối chiếu", task_type.name, "high", None, None, 2.5, self.member.username))
        workbook["Tasks"].append(("Dòng lỗi", None, None, "missing", None, None, 1, None))

        def upload():
            buffer = BytesIO()
            workbook.save(buffer)
            return SimpleUploadedFile("tasks.xlsx", buffer.getvalue())

        url = reverse("projects:task_import", args=[self.project.pk])
        self.assertContains(self.client.post(url, {"file": upload()}), "Dòng 3")
        self.assertEqual(self.project.tasks.count(), 1)
        workbook["Tasks"].delete_rows(3)
        fixed = upload().read()
        self.assertEqual(self.client.post(url, {"file": SimpleUploadedFile("tasks.xlsx", fixed)}).status_code, 302)
        self.assertContains(self.client.post(url, {"file": SimpleUploadedFile("tasks.xlsx", fixed)}), "đã được nhập")
        imported = self.project.tasks.get(title="Review đăng nhập")
        self.assertEqual(imported.status, self.todo)
        self.assertEqual(imported.task_type, task_type)
        self.assertTrue(imported.assignments.filter(user=self.member).exists())
        self.assertEqual(TaskImport.objects.get(project=self.project).task_count, 1)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_member_report_and_export_only_include_assigned_tasks(self):
        secret = create_task(self.manager, self.project, {"title": "Việc chưa giao", "priority": self.priority})
        self.task.due_date = date.today() - timedelta(days=1)
        self.task.save()
        self.client.force_login(self.member)
        response = self.client.get(reverse("projects:reports", args=[self.project.pk]), {"focus": "all"})
        self.assertContains(response, self.task.title)
        self.assertNotContains(response, secret.title)
        self.assertNotContains(response, "Tải công việc theo thành viên")
        response = self.client.get(reverse("reports:home"), {"focus": "all", "export": "csv"})
        self.assertContains(response, self.task.code)
        self.assertNotContains(response, secret.code)
        response = self.client.get(reverse("reports:home"), {"focus": "all", "export": "pdf"})
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.client.force_login(self.manager)
        response = self.client.get(reverse("reports:home"))
        self.assertContains(response, self.task.title)
        self.assertNotContains(response, secret.title)

    def test_quick_create_resolves_type_for_selected_project(self):
        self.client.force_login(self.manager)
        task_type = TaskType.objects.create(project=self.project, name="Kiểm thử")
        data = {"title": "Việc tạo nhanh", "project_id": self.project.pk,
                "priority_id": self.priority.pk, "task_type": task_type.pk}
        self.assertEqual(self.client.post(reverse("tasks:quick_create"), data).status_code, 302)
        task = Task.objects.get(title="Việc tạo nhanh")
        self.assertEqual(task.task_type, task_type)
        self.assertEqual(task.status, self.todo)

    def test_manager_report_is_limited_to_managed_projects(self):
        other = User.objects.create_user("other_owner", "owner@test.local", "Test@123", role=User.Role.PROJECT_MANAGER)
        unrelated = create_project(other, {
            "name": "Dự án cộng tác", "start_date": self.project.start_date, "end_date": self.project.end_date,
            "status": self.project.status, "priority": self.project.priority,
        })
        add_project_member(unrelated, self.manager, ProjectMember.Role.MEMBER, other)
        task = create_task(other, unrelated, {"title": "Việc dự án cộng tác", "priority": self.priority}, [self.manager.pk])
        self.client.force_login(self.manager)
        report = reverse("reports:home")
        self.assertNotContains(self.client.get(report, {"focus": "all"}), task.title)
        self.assertContains(self.client.get(report, {"focus": "all", "scope": "mine"}), task.title)

    def test_kanban_permission_outsider(self):
        self.client.force_login(self.outsider)
        response = self.client.post(
            reverse("tasks:ajax_status", args=[self.task.id]),
            data='{"status_id": %s}' % self.doing.id,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_member_can_change_own_task_status(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("tasks:ajax_status", args=[self.task.id]),
            data='{"status_id": %s}' % self.doing.id,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status.slug, "in-progress")

    def test_assignee_can_delete_individual_checklist_item(self):
        self.client.force_login(self.member)
        keep = TaskChecklist.objects.create(task=self.task, title="Giữ hạng mục này", is_completed=True)
        response = self.client.post(reverse("tasks:ajax_checklist_add", args=[self.task.pk]), {"title": "Mục cần xóa"})
        item_id = response.json()["id"]
        url = reverse("tasks:ajax_checklist_delete", args=[item_id])
        self.assertIn(url, response.json()["html"])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(self.client.post(url).json()["success"])
        self.assertFalse(TaskChecklist.objects.filter(pk=item_id).exists())
        self.assertTrue(TaskChecklist.objects.filter(pk=keep.pk, is_completed=True).exists())

    def test_checklist_delete_requires_write_access_to_task(self):
        add_project_member(self.project, self.outsider, ProjectMember.Role.MEMBER, self.manager)
        item = TaskChecklist.objects.create(task=self.task, title="Không xóa")
        url = reverse("tasks:ajax_checklist_delete", args=[item.pk])
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(self.task.get_absolute_url()), url)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.manager)
        self.client.post(reverse("projects:archive", args=[self.project.pk]))
        self.assertNotContains(self.client.get(self.task.get_absolute_url()), url)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(TaskChecklist.objects.filter(pk=item.pk).exists())

    def test_comment_creates_record(self):
        comment = add_comment(self.task, self.member, "Đã bắt đầu triển khai.")
        self.assertEqual(TaskComment.objects.filter(pk=comment.pk).count(), 1)

    def test_member_cannot_edit_foreign_task(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("tasks:edit", args=[self.task.id]))
        self.assertEqual(response.status_code, 403)

    def test_deadline_badges(self):
        self.task.due_date = date.today() + timedelta(days=2)
        self.task.status = self.todo
        self.task.save()
        self.assertTrue(self.task.is_due_soon)
        self.task.due_date = date.today() - timedelta(days=1)
        self.task.save()
        self.assertTrue(self.task.is_overdue)
