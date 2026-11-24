from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)

    def delete(self):
        return self.update(is_deleted=True, deleted_at=timezone.now())


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class Status(models.Model):
    class Scope(models.TextChoices):
        PROJECT = "PROJECT", "Project"
        TASK = "TASK", "Task"

    class Stage(models.TextChoices):
        TODO = "todo", "Mới"
        ACTIVE = "in-progress", "Đang làm"
        PAUSED = "paused", "Tạm hoãn"
        DELAYED = "delayed", "Báo chậm"
        REVIEW = "review", "Chờ duyệt"
        REWORK = "rework", "Cần làm lại"
        COMPLETED = "completed", "Đã duyệt"
        REJECTED = "rejected", "Đã từ chối"

    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)
    color = models.CharField(max_length=16, default="#6B7280")
    sort_order = models.PositiveIntegerField(default=0)
    scope = models.CharField(max_length=10, choices=Scope.choices)
    stage = models.CharField(max_length=20, choices=Stage.choices, blank=True, default="")
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="custom_task_statuses",
    )

    class Meta:
        ordering = ["sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["scope", "slug"], name="uniq_status_scope_slug"),
        ]

    def __str__(self):
        return self.name

    @property
    def is_completed(self):
        return self.stage == "completed"

    @property
    def is_closed(self):
        return self.stage in ("completed", "rejected")


class Priority(models.Model):
    class Scope(models.TextChoices):
        PROJECT = "PROJECT", "Project"
        TASK = "TASK", "Task"

    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)
    color = models.CharField(max_length=16, default="#6B7280")
    sort_order = models.PositiveIntegerField(default=0)
    scope = models.CharField(max_length=10, choices=Scope.choices)

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["scope", "slug"], name="uniq_priority_scope_slug"),
        ]

    def __str__(self):
        return self.name
