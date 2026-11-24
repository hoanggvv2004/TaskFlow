from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.db.models import OuterRef, Prefetch, Subquery

from core.models import SoftDeleteModel, TimeStampedModel
from core.utils import days_remaining


class ProjectQuerySet(models.QuerySet):
    def with_current(self):
        if "current_status_id" in getattr(self.query, "annotations", {}):
            return self
        status_links = ProjectStatus.objects.filter(
            project=OuterRef("pk"),
            is_current=True,
        )
        priority_links = ProjectPriority.objects.filter(
            project=OuterRef("pk"),
            is_current=True,
        )
        queryset = self.annotate(
            current_status_id=Subquery(status_links.values("status_id")[:1]),
            current_status_name=Subquery(status_links.values("status__name")[:1]),
            current_status_slug=Subquery(status_links.values("status__slug")[:1]),
            current_status_order=Subquery(status_links.values("status__sort_order")[:1]),
            current_priority_id=Subquery(priority_links.values("priority_id")[:1]),
            current_priority_name=Subquery(priority_links.values("priority__name")[:1]),
            current_priority_order=Subquery(priority_links.values("priority__sort_order")[:1]),
        ).prefetch_related(
            Prefetch(
                "status_links",
                queryset=ProjectStatus.objects.filter(is_current=True).select_related("status"),
                to_attr="_prefetched_current_status_links",
            ),
            Prefetch(
                "priority_links",
                queryset=ProjectPriority.objects.filter(is_current=True).select_related("priority"),
                to_attr="_prefetched_current_priority_links",
            ),
        )
        queryset._with_current_applied = True
        return queryset


class ProjectManager(models.Manager.from_queryset(ProjectQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Project(TimeStampedModel, SoftDeleteModel):
    code = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    department = models.ForeignKey(
        "accounts.Department", verbose_name="Phòng phụ trách", null=True, blank=True,
        on_delete=models.PROTECT, related_name="projects",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_projects",
    )
    cover_image = models.ImageField(upload_to="projects/", blank=True, null=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    objects = ProjectManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["end_date"]),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"

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
            raise ValueError("Project requires a status")
        if is_new and pending_priority is None:
            raise ValueError("Project requires a priority")
        super().save(*args, **kwargs)
        if pending_status is not None:
            delattr(self, "_pending_status")
            self.set_status(pending_status)
        if pending_priority is not None:
            delattr(self, "_pending_priority")
            self.set_priority(pending_priority)
        if is_new and not self.code:
            self.code = f"PRJ-{self.pk:04d}"
            super().save(update_fields=["code"])

    def set_status(self, status, actor=None):
        status_id = status.pk if hasattr(status, "pk") else status
        if status_id is None:
            raise ValueError("Project requires a status")
        current_status_id = None
        if self.pk:
            current_status_id = ProjectStatus.objects.filter(
                project_id=self.pk,
                is_current=True,
            ).values_list("status_id", flat=True).first()
        if current_status_id == status_id:
            if not self.pk:
                self._pending_status = status
            return
        with transaction.atomic():
            current = ProjectStatus.objects.select_for_update().filter(
                project_id=self.pk,
                is_current=True,
            )
            current.update(is_current=None)
            ProjectStatus.objects.create(
                project=self,
                status_id=status_id,
                is_current=True,
                changed_by=actor,
            )
        self._invalidate_status_cache()

    def set_priority(self, priority, actor=None):
        priority_id = priority.pk if hasattr(priority, "pk") else priority
        if priority_id is None:
            raise ValueError("Project requires a priority")
        current_priority_id = None
        if self.pk:
            current_priority_id = ProjectPriority.objects.filter(
                project_id=self.pk,
                is_current=True,
            ).values_list("priority_id", flat=True).first()
        if current_priority_id == priority_id:
            if not self.pk:
                self._pending_priority = priority
            return
        with transaction.atomic():
            current = ProjectPriority.objects.select_for_update().filter(
                project_id=self.pk,
                is_current=True,
            )
            current.update(is_current=None)
            ProjectPriority.objects.create(
                project=self,
                priority_id=priority_id,
                is_current=True,
                changed_by=actor,
            )
        self._invalidate_priority_cache()

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.pk])

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Ngày kết thúc không được trước ngày bắt đầu."})

    @property
    def days_left(self):
        return days_remaining(self.end_date)

    def task_stats(self):
        tasks = self.tasks.with_current()
        total = tasks.count()
        completed = tasks.filter(current_stage="completed").count()
        overdue = tasks.overdue().count()
        return {
            "total": total,
            "completed": completed,
            "overdue": overdue,
            "progress": int(round((completed / total) * 100)) if total else 0,
        }

    def progress(self):
        return self.task_stats()["progress"]

    @property
    def status(self):
        if hasattr(self, "_pending_status"):
            value = self._pending_status
            return value if hasattr(value, "pk") else None
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
            return value if hasattr(value, "pk") else None
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
        self.status_links.filter(is_current=True).select_related("status").first()

    def _invalidate_priority_cache(self):
        for name in ("_cached_priority", "_cached_priority_id", "_prefetched_current_priority_links"):
            if hasattr(self, name):
                delattr(self, name)


class ProjectStatus(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="status_links")
    status = models.ForeignKey(
        "core.Status",
        on_delete=models.PROTECT,
        related_name="project_links",
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
                fields=["project", "is_current"],
                name="uniq_project_status_current",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "changed_at"], name="idx_project_status_changed"),
        ]

    def __str__(self):
        return f"{self.project.code} - {self.status.name}"


class ProjectPriority(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="priority_links")
    priority = models.ForeignKey(
        "core.Priority",
        on_delete=models.PROTECT,
        related_name="project_links",
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
                fields=["project", "is_current"],
                name="uniq_project_priority_current",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "changed_at"], name="idx_project_priority_changed"),
        ]

    def __str__(self):
        return f"{self.project.code} - {self.priority.name}"


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Project Owner"
        MANAGER = "MANAGER", "Project Manager"
        MEMBER = "MEMBER", "Member"
        VIEWER = "VIEWER", "Viewer"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_project_members",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="uniq_project_member"),
        ]
        indexes = [models.Index(fields=["project", "role"])]

    def __str__(self):
        return f"{self.user} @ {self.project.code} ({self.role})"
