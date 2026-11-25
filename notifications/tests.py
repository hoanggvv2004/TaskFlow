from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.models import Priority, Status
from notifications.models import Notification
from projects.models import ProjectMember
from projects.services import add_project_member, create_project
from tasks.services import create_task


class NotificationTests(TestCase):
    def setUp(self):
        Status.objects.get_or_create(scope="PROJECT", slug="active", defaults={"name": "Active", "sort_order": 1})
        Priority.objects.get_or_create(scope="PROJECT", slug="medium", defaults={"name": "Medium", "sort_order": 2})
        Status.objects.get_or_create(scope="TASK", slug="todo", defaults={"name": "To-do", "sort_order": 1})
        Priority.objects.get_or_create(scope="TASK", slug="medium", defaults={"name": "Medium", "sort_order": 2})
        self.manager = User.objects.create_user(
            "manager", "manager@test.local", "Manager@123", role=User.Role.PROJECT_MANAGER, first_name="Lan"
        )
        self.member = User.objects.create_user("member", "member@test.local", "Member@123", role=User.Role.MEMBER, first_name="Bao")
        self.project = create_project(
            self.manager,
            {
                "name": "AI Customer Support",
                "description": "AI",
                "category": "AI",
                "start_date": date.today(),
                "end_date": date.today() + timedelta(days=20),
                "status": Status.objects.get(scope="PROJECT", slug="active"),
                "priority": Priority.objects.get(scope="PROJECT", slug="medium"),
            },
        )
        add_project_member(self.project, self.member, ProjectMember.Role.MEMBER, self.manager)

    def test_assign_creates_notification(self):
        create_task(
            self.manager,
            self.project,
            {
                "title": "Thiết kế Dashboard",
                "description": "",
                "status": Status.objects.get(scope="TASK", slug="todo"),
                "priority": Priority.objects.get(scope="TASK", slug="medium"),
                "due_date": date.today() + timedelta(days=4),
                "progress": 0,
            },
            [self.member.id],
        )
        self.assertTrue(
            Notification.objects.filter(user=self.member, type=Notification.Type.TASK_ASSIGNED).exists()
        )

    def test_mark_all_read(self):
        Notification.objects.create(
            user=self.member,
            type=Notification.Type.TASK_UPDATED,
            title="Test",
            message="msg",
            url="/",
        )
        self.client.force_login(self.member)
        response = self.client.post(reverse("notifications:read_all"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Notification.objects.filter(user=self.member, is_read=False).exists())
