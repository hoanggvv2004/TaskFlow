

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models import OuterRef, Prefetch, Subquery
from django.urls import reverse
from django.utils import timezone

from core.models import SoftDeleteModel, SoftDeleteQuerySet, TimeStampedModel
from core.utils import is_due_soon, is_overdue


CLOSED_STAGES = ("completed", "rejected")


class TaskWorkflow(models.Model):
    project = models.OneToOneField("projects.Project", on_delete=models.CASCADE, related_name="task_workflow")
    initial_status = models.ForeignKey("core.Status", on_delete=models.PROTECT, related_name="+")
    statuses = models.ManyToManyField("core.Status", related_name="+")


class TaskTransition(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Quản lý dự án"
        ASSIGNEE = "assignee", "Người được giao"

    workflow = models.ForeignKey(TaskWorkflow, on_delete=models.CASCADE, related_name="transitions")
    source = models.ForeignKey("core.Status", on_delete=models.PROTECT, related_name="+")
    target = models.ForeignKey("core.Status", on_delete=models.PROTECT, related_name="+")
    role = models.CharField(max_length=12, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workflow", "source", "target", "role"], name="unique_task_transition"),
        ]


class TaskType(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="task_types")
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_project_task_type"),
        ]

    def __str__(self):
        return self.name


class TaskImport(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="task_imports")
    digest = models.CharField(max_length=64)
    task_count = models.PositiveIntegerField()
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "digest"], name="unique_project_task_import"),
        ]


class TaskQuerySet(SoftDeleteQuerySet):
    def with_current(self):
        if "current_status_id" in getattr(self.query, "annotations", {}):
            return self
        status_links = TaskStatus.objects.filter(
            task=OuterRef("pk"),
            is_current=True,
        )
        priority_links = TaskPriority.objects.filter(
            task=OuterRef("pk"),
            is_current=True,
        )
        queryset = self.annotate(
            current_status_id=Subquery(status_links.values("status_id")[:1]),
            current_status_name=Subquery(status_links.values("status__name")[:1]),
            current_status_slug=Subquery(status_links.values("status__slug")[:1]),
            current_status_order=Subquery(status_links.values("status__sort_order")[:1]),
            current_stage=Subquery(status_links.values("status__stage")[:1]),
            current_priority_id=Subquery(priority_links.values("priority_id")[:1]),
            current_priority_name=Subquery(priority_links.values("priority__name")[:1]),
            current_priority_order=Subquery(priority_links.values("priority__sort_order")[:1]),
        ).prefetch_related(
            Prefetch(
                "status_links",
                queryset=TaskStatus.objects.filter(is_current=True).select_related("status"),
                to_attr="_prefetched_current_status_links",
            ),
            Prefetch(
                "priority_links",
                queryset=TaskPriority.objects.filter(is_current=True).select_related("priority"),
                to_attr="_prefetched_current_priority_links",
            ),
        )
        queryset._with_current_applied = True
        return queryset

    def open_tasks(self):
        return self.with_current().exclude(current_stage__in=CLOSED_STAGES)

    def overdue(self):
        return self.open_tasks().filter(due_date__lt=timezone.localdate())

    def focused(self, focus, user):
        if focus == "overdue":
            return self.overdue()
        if focus == "due_soon":
            today = timezone.localdate()
            return self.open_tasks().filter(due_date__range=(today, today + timedelta(days=3)))
        if focus == "assigned":
            return self.filter(assignments__user=user)
        if focus == "unassigned":
            return self.open_tasks().filter(assignments__isnull=True)
        if focus in {"review", "rework", "completed"}:
            return self.with_current().filter(current_stage=focus)
        return self


class TaskManager(models.Manager.from_queryset(TaskQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive().filter(project__is_deleted=False)


class Task(TimeStampedModel, SoftDeleteModel):
    code = models.CharField(max_length=20, unique=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="tasks")
    task_type = models.ForeignKey(TaskType, null=True, blank=True, on_delete=models.PROTECT, related_name="tasks")
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    actual_hours = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    progress = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tasks",
    )
    assignees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="TaskAssignment",
        through_fields=("task", "user"),
        related_name="assigned_tasks",
        blank=True,
    )
    objects = TaskManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.code} {self.title}"

    def refresh_from_db(self, using=None, fields=None, from_queryset=None):
        super().refresh_from_db(using=using, fields=fields, from_queryset=from_queryset)
        self._invalidate_status_cache()
        self._invalidate_priority_cache()
        for pending in ("_pending_status", "_pending_priority"):
            if hasattr(self, pending):
                delattr(self, pending)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        pending_status = getattr(self, "_pending_status", None)
        pending_priority = getattr(self, "_pending_priority", None)
        if is_new and pending_status is None:
            raise ValueError("Task requires a status")
        if is_new and pending_priority is None:
            raise ValueError("Task requires a priority")
        status = pending_status or self.status
        if status is not None and hasattr(status, "pk"):
            pass
        elif status is not None:
            from core.models import Status
            status = Status._default_manager.filter(pk=status).first()
        if getattr(status, "is_completed", False):
            self.progress = 100
        elif self.progress == 100:
            self.progress = 90
        super().save(*args, **kwargs)
        if pending_status is not None:
            delattr(self, "_pending_status")
            self.set_status(pending_status)
        if pending_priority is not None:
            delattr(self, "_pending_priority")
            self.set_priority(pending_priority)
        if is_new and not self.code:
            self.code = f"TASK-{self.pk:05d}"
            super().save(update_fields=["code"])

    def set_status(self, status, actor=None):
        status_id = status.pk if hasattr(status, "pk") else status
        if status_id is None:
            raise ValueError("Task requires a status")
        current_status_id = None
        if self.pk:
            current_status_id = TaskStatus.objects.filter(
                task_id=self.pk,
                is_current=True,
            ).values_list("status_id", flat=True).first()
        if current_status_id == status_id:
            if not self.pk:
                self._pending_status = status
            return
        with transaction.atomic():
            current = TaskStatus.objects.select_for_update().filter(
                task_id=self.pk,
                is_current=True,
            )
            current.update(is_current=None)
            TaskStatus.objects.create(
                task=self,
                status_id=status_id,
                is_current=True,
                changed_by=actor,
            )
        self._invalidate_status_cache()

    def set_priority(self, priority, actor=None):
        priority_id = priority.pk if hasattr(priority, "pk") else priority
        if priority_id is None:
            raise ValueError("Task requires a priority")
        current_priority_id = None
        if self.pk:
            current_priority_id = TaskPriority.objects.filter(
                task_id=self.pk,
                is_current=True,
            ).values_list("priority_id", flat=True).first()
        if current_priority_id == priority_id:
            if not self.pk:
                self._pending_priority = priority
            return
        with transaction.atomic():
            current = TaskPriority.objects.select_for_update().filter(
                task_id=self.pk,
                is_current=True,
            )
            current.update(is_current=None)
            TaskPriority.objects.create(
                task=self,
                priority_id=priority_id,
                is_current=True,
                changed_by=actor,
            )
        self._invalidate_priority_cache()

    def get_absolute_url(self):
        return reverse("tasks:detail", args=[self.pk])

    def clean(self):
        errors = {}
        if self.start_date and self.due_date and self.start_date > self.due_date:
            errors["due_date"] = "Hạn hoàn thành phải từ ngày bắt đầu trở đi."
        if self.task_type_id and self.task_type.project_id != self.project_id:
            errors["task_type"] = "Loại công việc phải thuộc dự án này."
        status = getattr(self, "_pending_status", None) or self.status
        if status is not None and not hasattr(status, "pk"):
            from core.models import Status
            status = Status._default_manager.filter(pk=status).first()
        if status is not None and hasattr(status, "pk") and status.project_id not in (None, self.project_id):
            errors["status"] = "Trạng thái phải thuộc dự án này."
        if errors:
            raise ValidationError(errors)

    @property
    def is_completed(self):
        status = self.status
        return False if status is None else status.is_completed

    @property
    def is_overdue(self):
        status = self.status
        if status is None:
            return False
        return is_overdue(self.due_date, status.is_closed)

    @property
    def is_due_soon(self):
        status = self.status
        if status is None:
            return False
        return not status.is_closed and is_due_soon(self.due_date)

    @property
    def status(self):
        if hasattr(self, "_pending_status"):
            value = self._pending_status
            if hasattr(value, "pk"):
                return value
            from core.models import Status
            return Status._default_manager.filter(pk=value).first()
        if hasattr(self, "_cached_status"):
            return self._cached_status
        if self.pk is None:
            return None
        links = getattr(self, "_prefetched_current_status_links", None)
        link = links[0] if links else self.status_links.filter(is_current=True).select_related("status").first()
        value = link.status if link else None
        self._cached_status = value
        return value

    @status.setter
    def status(self, value):
        self._pending_status = value

    @property
    def status_id(self):
        if hasattr(self, "_pending_status"):
            value = self._pending_status
            return value.pk if hasattr(value, "pk") else value
        if hasattr(self, "_cached_status_id"):
            return self._cached_status_id
        if self.pk is None:
            return None
        links = getattr(self, "_prefetched_current_status_links", None)
        link = links[0] if links else self.status_links.filter(is_current=True).only("status_id").first()
        value = link.status_id if link else None
        self._cached_status_id = value
        return value

    @status_id.setter
    def status_id(self, value):
        self._pending_status = value

    @property
    def priority(self):
        if hasattr(self, "_pending_priority"):
            value = self._pending_priority
            if hasattr(value, "pk"):
                return value
            from core.models import Priority
            return Priority._default_manager.filter(pk=value).first()
        if hasattr(self, "_cached_priority"):
            return self._cached_priority
        if self.pk is None:
            return None
        links = getattr(self, "_prefetched_current_priority_links", None)
        link = links[0] if links else self.priority_links.filter(is_current=True).select_related("priority").first()
        value = link.priority if link else None
        self._cached_priority = value
        return value

    @priority.setter
    def priority(self, value):
        self._pending_priority = value

    @property
    def priority_id(self):
        if hasattr(self, "_pending_priority"):
            value = self._pending_priority
            return value.pk if hasattr(value, "pk") else value
        if hasattr(self, "_cached_priority_id"):
            return self._cached_priority_id
        if self.pk is None:
            return None
        links = getattr(self, "_prefetched_current_priority_links", None)
        link = links[0] if links else self.priority_links.filter(is_current=True).only("priority_id").first()
        value = link.priority_id if link else None
        self._cached_priority_id = value
        return value

    @priority_id.setter
    def priority_id(self, value):
        self._pending_priority = value

    def _invalidate_status_cache(self):
        for name in ("_cached_status", "_cached_status_id", "_prefetched_current_status_links"):
            if hasattr(self, name):
                delattr(self, name)

    def _invalidate_priority_cache(self):
        for name in ("_cached_priority", "_cached_priority_id", "_prefetched_current_priority_links"):
            if hasattr(self, name):
                delattr(self, name)


class TaskStatus(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="status_links")
    status = models.ForeignKey(
        "core.Status",
        on_delete=models.PROTECT,
        related_name="task_links",
    )
    is_current = models.BooleanField(null=True, default=None)
    changed_at = models.DateTimeField(default=timezone.now)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "is_current"],
                name="uniq_task_status_current",
            ),
        ]
        indexes = [
            models.Index(fields=["task", "changed_at"], name="idx_task_status_changed"),
        ]

    def __str__(self):
        return f"{self.task.code} - {self.status.name}"


class TaskPriority(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="priority_links")
    priority = models.ForeignKey(
        "core.Priority",
        on_delete=models.PROTECT,
        related_name="task_links",
    )
    is_current = models.BooleanField(null=True, default=None)
    changed_at = models.DateTimeField(default=timezone.now)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "is_current"],
                name="uniq_task_priority_current",
            ),
        ]
        indexes = [
            models.Index(fields=["task", "changed_at"], name="idx_task_priority_changed"),
        ]

    def __str__(self):
        return f"{self.task.code} - {self.priority.name}"


class TaskAssignment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_assignments_made",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "user"], name="uniq_task_assignment"),
        ]

    def __str__(self):
        return f"{self.task.code} -> {self.user}"


class TaskComment(TimeStampedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_comments")
    content = models.TextField()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment #{self.pk} on {self.task.code}"


class TaskChecklist(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="checklist_items")
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_checklist_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title


class TaskHistory(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="task_status_changes",
    )
    old_status = models.ForeignKey(
        "core.Status",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    new_status = models.ForeignKey("core.Status", on_delete=models.SET_NULL, null=True, related_name="+")
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Document(TimeStampedModel):
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    original_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    file_size = models.PositiveIntegerField(default=0)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_documents",
    )
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
from datetime import timedelta

