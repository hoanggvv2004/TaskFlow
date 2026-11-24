from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Department, User
from activity.services import log_activity
from core.permissions import can_create_project, can_edit_project_settings, can_manage_project, is_admin
from notifications.models import Notification
from notifications.services import notify
from projects.models import Project, ProjectMember


def lock_project(project_id):
    try:
        return Project.objects.select_for_update().get(pk=project_id)
    except Project.DoesNotExist:
        raise PermissionDenied("Dự án không còn khả dụng.")


def lock_managed_project(project_id, actor):
    project = lock_project(project_id)
    if not can_manage_project(actor, project):
        raise PermissionDenied("Bạn không có quyền cập nhật dự án này.")
    return project


def project_has_work(project):
    from tasks.models import Document, Task

    return (
        Task.all_objects.filter(project=project).exists()
        or Document.objects.filter(project=project).exists()
        or project.activity_logs.filter(action__in=["task_created", "document_uploaded"]).exists()
    )


@transaction.atomic
def change_project_lifecycle(project_id, actor, action):
    if action not in {"archive", "restore", "delete"}:
        raise ValueError("Thao tác vòng đời không hợp lệ.")
    project = lock_project(project_id)
    if not can_edit_project_settings(actor, project):
        raise PermissionDenied("Chỉ Owner hoặc Admin mới thay đổi vòng đời dự án.")
    if action == "delete":
        if project_has_work(project):
            raise ValidationError("Dự án đã phát sinh công việc hoặc tài liệu. Hãy lưu trữ dự án.")
        project.delete()
        log_message = "Xóa dự án trống"
    else:
        archived_at = timezone.now() if action == "archive" else None
        if bool(project.archived_at) == bool(archived_at):
            return project
        project.archived_at = archived_at
        project.save(update_fields=["archived_at", "updated_at"])
        log_message = "Lưu trữ dự án" if archived_at else "Kích hoạt lại dự án"
    log_activity(actor, f"project_{action}", f"{log_message} {project.code}.", project=project)
    return project


@transaction.atomic
def create_project(owner, cleaned, cover=None):
    owner = User.objects.select_for_update().get(pk=owner.pk)
    if not can_create_project(owner):
        raise PermissionDenied("Chỉ trưởng phòng hoặc Admin mới được mở dự án cho phòng ban.")
    department = cleaned.get("department")
    if owner.department_id and not is_admin(owner) and (not department or department.pk != owner.department_id):
        raise ValidationError("Trưởng phòng chỉ được mở dự án cho phòng mình.")
    if department:
        department = Department.objects.select_for_update().filter(pk=department.pk, is_active=True).first()
        if not department or (not is_admin(owner) and department.manager_id != owner.pk):
            raise ValidationError("Phòng ban đã ngừng hoạt động hoặc bạn không phụ trách phòng này.")
    project = Project(**cleaned)
    project.owner = owner
    if cover:
        project.cover_image = cover
    project.full_clean(exclude={"legacy_status", "legacy_priority"})
    project.save()
    ProjectMember.objects.get_or_create(
        project=project,
        user=owner,
        defaults={"role": ProjectMember.Role.OWNER, "added_by": owner},
    )
    log_activity(
        owner,
        "project_created",
        f"{owner.get_display_name()} tạo dự án {project.name}.",
        project=project,
    )
    return project


def eligible_project_users(project):
    users = User.objects.filter(is_active=True)
    if project.department_id:
        users = users.filter(department_id=project.department_id)
    return users


@transaction.atomic
def add_project_member(project, user, role, added_by):
    project = lock_managed_project(project.pk, added_by)
    user = eligible_project_users(project).select_for_update().filter(pk=user.pk).first()
    if not user:
        raise ValueError("Chỉ thêm nhân sự đang hoạt động thuộc phòng phụ trách dự án.")
    member, created = ProjectMember.objects.get_or_create(
        project=project,
        user=user,
        defaults={"role": role, "added_by": added_by},
    )
    if not created:
        raise ValueError("Thành viên đã thuộc dự án này.")
    log_activity(
        added_by,
        "member_added",
        f"{user.get_display_name()} được thêm vào dự án.",
        project=project,
    )
    notify(
        user,
        Notification.Type.PROJECT_MEMBER_ADDED,
        "Bạn được thêm vào dự án",
        f"{added_by.get_display_name()} đã thêm bạn vào {project.name}.",
        project.get_absolute_url(),
    )
    return member


@transaction.atomic
def remove_project_member(project, member, actor):
    project = lock_managed_project(project.pk, actor)
    member = project.members.get(pk=member.pk)
    if member.role == ProjectMember.Role.OWNER:
        raise ValueError("Không thể xóa Project Owner khi chưa chuyển quyền.")
    if member.user_id == project.owner_id:
        raise ValueError("Không thể xóa chủ sở hữu dự án khi chưa chuyển quyền.")
    if project.tasks.open_tasks().filter(assignments__user_id=member.user_id).exists():
        raise ValueError("Hãy chuyển công việc đang phân công trước khi xóa thành viên.")
    user = member.user
    member.delete()
    log_activity(
        actor,
        "member_removed",
        f"{user.get_display_name()} đã bị xóa khỏi dự án.",
        project=project,
    )


@transaction.atomic
def change_member_role(project, member, role, actor):
    project = lock_managed_project(project.pk, actor)
    member = project.members.get(pk=member.pk)
    if member.role == ProjectMember.Role.OWNER and role != ProjectMember.Role.OWNER:
        raise ValueError("Không thể hạ quyền Owner khi chưa chuyển quyền sở hữu.")
    if role == ProjectMember.Role.OWNER and member.user_id != project.owner_id:
        raise ValueError("Hãy dùng chức năng chuyển quyền sở hữu.")
    if role == ProjectMember.Role.VIEWER and project.tasks.open_tasks().filter(assignments__user_id=member.user_id).exists():
        raise ValueError("Hãy chuyển công việc đang phân công trước khi đổi sang Viewer.")
    old = member.get_role_display()
    member.role = role
    member.save(update_fields=["role"])
    log_activity(
        actor,
        "member_role_changed",
        f"Vai trò của {member.user.get_display_name()} được đổi thành {member.get_role_display()}.",
        project=project,
        old_value=old,
        new_value=member.get_role_display(),
    )
    return member


@transaction.atomic
def transfer_owner(project, new_owner, actor):
    project = lock_managed_project(project.pk, actor)
    if not can_edit_project_settings(actor, project):
        raise PermissionDenied("Chỉ Owner hoặc Admin mới chuyển quyền sở hữu.")
    old_owner = project.owner
    current = ProjectMember.objects.filter(project=project, user=old_owner).first()
    incoming = ProjectMember.objects.filter(project=project, user=new_owner).first()
    if not incoming:
        incoming = ProjectMember.objects.create(
            project=project,
            user=new_owner,
            role=ProjectMember.Role.OWNER,
            added_by=actor,
        )
    else:
        incoming.role = ProjectMember.Role.OWNER
        incoming.save(update_fields=["role"])
    if current and current.user_id != new_owner.id:
        current.role = ProjectMember.Role.MANAGER
        current.save(update_fields=["role"])
    project.owner = new_owner
    project.save(update_fields=["owner", "updated_at"])
    log_activity(
        actor,
        "owner_transferred",
        f"Quyền sở hữu dự án được chuyển cho {new_owner.get_display_name()}.",
        project=project,
        old_value=old_owner.get_display_name(),
        new_value=new_owner.get_display_name(),
    )
