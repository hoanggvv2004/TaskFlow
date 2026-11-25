from django.test import TestCase

from accounts.models import User
from core.models import Status, Priority
from projects.models import Project
from tasks.models import Task, TaskStatus, TaskPriority


class CurrentStatusTaskTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "owner",
            "owner@test.local",
            "Owner@123",
        )
        project_status = Status.objects.create(
            name="Active",
            slug="active",
            scope="PROJECT",
        )
        project_priority = Priority.objects.create(
            name="Medium",
            slug="medium",
            scope="PROJECT",
        )
        self.project = Project.objects.create(
            name="Project",
            start_date="2026-01-01",
            end_date="2026-12-31",
            owner=self.owner,
            status=project_status,
            priority=project_priority,
        )
        self.status_1, _ = Status.objects.get_or_create(
            scope="TASK",
            slug="todo",
            defaults={"name": "Todo", "stage": "todo"},
        )
        self.status_2, _ = Status.objects.get_or_create(
            scope="TASK",
            slug="doing",
            defaults={"name": "Doing", "stage": "in-progress"},
        )
        self.priority, _ = Priority.objects.get_or_create(
            scope="TASK",
            slug="high",
            defaults={"name": "High"},
        )

    def test_create_change_status_and_missing_status(self):
        task = Task(
            title="Task",
            project=self.project,
            created_by=self.owner,
            priority=self.priority,
            status=self.status_1,
        )
        task.save()

        self.assertEqual(task.status, self.status_1)
        self.assertEqual(TaskStatus.objects.filter(task=task, is_current=True).count(), 1)

        task.set_status(self.status_2)
        task.save()

        self.assertEqual(task.status, self.status_2)
        self.assertEqual(TaskStatus.objects.filter(task=task, is_current=True).count(), 1)
        self.assertEqual(TaskStatus.objects.filter(task=task, is_current=None).count(), 1)

        fetched = Task.objects.with_current().get(pk=task.pk)
        self.assertEqual(fetched.current_status_id, self.status_2.pk)
        self.assertEqual(fetched.current_status_slug, "doing")

        with self.assertRaises(ValueError):
            Task(
                title="Missing status",
                project=self.project,
                created_by=self.owner,
                priority=self.priority,
            ).save()
