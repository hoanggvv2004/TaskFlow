from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import SoftDeleteQuerySet


class Department(models.Model):
    code = models.SlugField("Mã phòng", max_length=20, unique=True)
    name = models.CharField("Tên phòng ban", max_length=100, unique=True)
    manager = models.OneToOneField(
        "accounts.User", verbose_name="Trưởng phòng", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="managed_department",
    )
    description = models.TextField("Mô tả", blank=True)
    is_active = models.BooleanField("Đang hoạt động", default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class ActiveUserQuerySet(SoftDeleteQuerySet):
    pass


class ActiveUserManager(UserManager):
    def get_queryset(self):
        return ActiveUserQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.MEMBER)
        return super().create_user(username, email=email, password=password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return super().create_superuser(username, email=email, password=password, **extra_fields)


class AllUserManager(UserManager):
    def get_queryset(self):
        return ActiveUserQuerySet(self.model, using=self._db)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        PROJECT_MANAGER = "PROJECT_MANAGER", "Project Manager"
        MEMBER = "MEMBER", "Member"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.MEMBER, db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    department = models.ForeignKey(
        Department, verbose_name="Phòng ban", null=True, blank=True,
        on_delete=models.PROTECT, related_name="staff",
    )
    bio = models.TextField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    language = models.CharField(max_length=10, default="vi")
    email_notification = models.BooleanField(default=True)
    browser_notification = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveUserManager()
    all_objects = AllUserManager()

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role", "is_active"]),
        ]

    def get_display_name(self):
        full_name = self.get_full_name().strip()
        return full_name or self.username

    def get_initials(self):
        name = self.get_display_name()
        parts = [part for part in name.replace(".", " ").split() if part]
        if not parts:
            return "U"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return f"{parts[0][0]}{parts[-1][0]}".upper()

    def get_absolute_url(self):
        return reverse("accounts:user_detail", args=[self.pk])

    def soft_delete(self):
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "is_active", "deleted_at"])

    def lock(self):
        self.is_active = False
        self.save(update_fields=["is_active"])

    def unlock(self):
        if not self.is_deleted:
            self.is_active = True
            self.save(update_fields=["is_active"])
