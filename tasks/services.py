import logging
import os

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from activity.services import log_activity
from core.models import Status
from core.permissions import can_manage_project, can_view_project, is_task_assignee
from core.validators import validate_upload_file
from notifications.models import Notification
from notifications.services import notify, notify_users
from projects.models import ProjectMember
from projects.services import eligible_project_users, lock_managed_project, lock_project
from tasks.models import Document, Task, TaskAssignment, TaskHistory
from tasks.workflow import allowed_targets, initial_status, workflow_actor, workflow_configuration

logger = logging.getLogger("taskflow")


def _assignee_users(task):
    return list(task.assignees.all())


def assignable_members(project):
    return ProjectMember.objects.filter(
        project=project, user__in=eligible_project_users(project),
    ).exclude(role=ProjectMember.Role.VIEWER)


def locked_task(task):
    project = lock_project(task.project_id)
    current = Task.all_objects.select_for_update().filter(pk=task.pk, project=project, is_deleted=False).first()
    if not current:
        raise PermissionDenied("Công việc không còn khả dụng.")
    current.project = project
    return current


def _validate_task_details(task):
    if (
        task.task_type_id
        and not task.project.task_types.filter(pk=task.task_type_id, is_active=True).exists()
    ):
        raise ValidationError("Hãy chọn một loại công việc đang dùng trong dự án.")


def _validate_deadline(task, confirmed):
    if task.due_date and task.due_date > task.project.end_date and not confirmed:
        raise ValidationError("Hạn task vượt quá deadline dự án. Hãy xác nhận nếu vẫn muốn tiếp tục.")


@transaction.atomic
def create_task(actor, project, cleaned, assignee_ids=None, warn_deadline=False):
    project = lock_managed_project(project.pk, actor)
    status = initial_status(project)
    if cleaned.get("status") not in (None, status):
        raise ValidationError("Công việc mới phải dùng trạng thái khởi đầu của dự án.")
    task = Task(project=project, created_by=actor, **{**cleaned, "status": status})
    _validate_deadline(task, warn_deadline)
    _validate_task_details(task)
    task.full_clean(exclude={"legacy_status", "legacy_priority"})
    task.save()
    TaskHistory.objects.create(task=task, user=actor, new_status=task.status, note="Tạo nhiệm vụ")
    log_activity(
        actor,
        "task_created",
        f"{actor.get_display_name()} tạo {task.code}.",
        project=project,
        task=task,
    )
    if assignee_ids:
        assign_users(task, assignee_ids, actor)
    return task


@transaction.atomic
def assign_users(task, user_ids, actor):
    task = locked_task(task)
    if not can_manage_project(actor, task.project):
        raise PermissionDenied("Chỉ quản lý mới được giao việc.")
    user_ids = set(user_ids)
    current_ids = set(task.assignments.values_list("user_id", flat=True))
    new_ids = user_ids - current_ids
    eligible_ids = assignable_members(task.project).filter(user_id__in=new_ids).values("user_id")
    users = list(eligible_project_users(task.project).select_for_update().filter(pk__in=eligible_ids).order_by("pk"))
    if new_ids != {user.pk for user in users}:
        raise ValidationError("Chỉ giao việc cho thành viên đang hoạt động và thuộc phòng phụ trách dự án.")
    for user in users:
        TaskAssignment.objects.create(task=task, user=user, assigned_by=actor)
        log_activity(
            actor,
            "task_assigned",
            f"{actor.get_display_name()} giao {task.code} cho {user.get_display_name()}.",
            project=task.project,
            task=task,
        )
        notify(
            user,
            Notification.Type.TASK_ASSIGNED,
            "Bạn được giao nhiệm vụ",
            f"{actor.get_display_name()} đã giao {task.code} cho bạn.",
            task.get_absolute_url(),
        )
    stale = task.assignments.exclude(user_id__in=user_ids)
    stale.delete()


@transaction.atomic
def edit_task(task, actor, cleaned, assignee_ids, confirm_outside=False):
    task = locked_task(task)
    if not can_manage_project(actor, task.project):
        raise PermissionDenied("Chỉ quản lý mới được sửa công việc.")
    editable = ("title", "description", "task_type", "start_date", "due_date",
                "estimated_hours", "actual_hours", "progress")
    if "priority" in cleaned:
        task.set_priority(cleaned["priority"], actor)
    previous_type = task.task_type_id
    for field in editable:
        setattr(task, field, cleaned[field])
    if task.task_type_id != previous_type:
        _validate_task_details(task)
    _validate_deadline(task, confirm_outside)
    task.full_clean(exclude={"legacy_status", "legacy_priority"})
    task.save(update_fields=[*editable, "updated_at"])
    assign_users(task, assignee_ids, actor)
    return task


@transaction.atomic
def delete_task(task, actor):
    task = locked_task(task)
    if not can_manage_project(actor, task.project):
        raise PermissionDenied("Chỉ quản lý mới được lưu trữ công việc.")
    task.delete()


@transaction.atomic
def update_task_status(task, new_status, actor, note="", expected_status_id=None):
    task = locked_task(task)
    task = Task.objects.with_current().select_for_update().filter(pk=task.pk).first()
    actor_permissions = workflow_actor(actor, task.project)
    if not actor_permissions[0] and not is_task_assignee(actor, task):
        raise PermissionDenied("Chỉ quản lý hoặc người được giao mới được đổi trạng thái.")
    old_status = task.status
    if old_status == new_status:
        return task
    if expected_status_id is not None and expected_status_id != old_status.pk:
        raise ValidationError("Trạng thái vừa thay đổi. Hãy tải lại trang rồi thử lại.")
    _, statuses, rules = workflow_configuration(task.project)
    if new_status not in allowed_targets(task, actor, statuses, rules, actor_permissions):
        raise ValidationError("Vai trò của bạn không được thực hiện bước chuyển này trong dự án.")
    if len(note) > 255:
        raise ValidationError("Ghi chú tối đa 255 ký tự.")
    task.set_status(new_status, actor)
    task.save(update_fields=["progress", "updated_at"])
    TaskHistory.objects.create(task=task, user=actor, old_status=old_status, new_status=new_status, note=note)
    log_activity(
        actor,
        "task_status_changed",
        f"{actor.get_display_name()} thay đổi {task.code} từ {old_status.name} sang {new_status.name}.",
        project=task.project,
        task=task,
        old_value=old_status.name if old_status else "",
        new_value=new_status.name,
    )
    if new_status.is_completed:
        notify_users(
            _assignee_users(task) + [task.created_by, task.project.owner],
            Notification.Type.TASK_COMPLETED,
            "Nhiệm vụ hoàn thành",
            f"{actor.get_display_name()} đã hoàn thành {task.code}.",
            task.get_absolute_url(),
            exclude_user=actor,
        )
    else:
        recipients = _assignee_users(task)
        if new_status.stage == Status.Stage.REVIEW:
            recipients.append(task.project.owner)
            recipients.extend(
                member.user for member in task.project.members.filter(role=ProjectMember.Role.MANAGER).select_related("user")
            )
        notify_users(
            recipients,
            Notification.Type.TASK_UPDATED,
            "Cập nhật trạng thái nhiệm vụ",
            f"{task.code} chuyển sang {new_status.name}.",
            task.get_absolute_url(),
            exclude_user=actor,
        )
    return task


@transaction.atomic
def change_deadline(task, new_due, actor, confirm_outside=False):
    task = locked_task(task)
    if not can_manage_project(actor, task.project):
        raise PermissionDenied("Chỉ quản lý mới được cập nhật thời hạn.")
    if new_due and task.project.end_date and new_due > task.project.end_date and not confirm_outside:
        raise ValidationError("Hạn task vượt quá deadline dự án.")
    old = task.due_date.isoformat() if task.due_date else ""
    task.due_date = new_due
    task.save(update_fields=["due_date", "updated_at"])
    log_activity(
        actor,
        "deadline_changed",
        f"{actor.get_display_name()} thay đổi deadline {task.code}.",
        project=task.project,
        task=task,
        old_value=old,
        new_value=new_due.isoformat() if new_due else "",
    )
    notify_users(
        _assignee_users(task),
        Notification.Type.DEADLINE_CHANGED,
        "Deadline đã thay đổi",
        f"Deadline của {task.code} đã được cập nhật.",
        task.get_absolute_url(),
        exclude_user=actor,
    )
    return task


def add_comment(task, user, content):
    from tasks.models import TaskComment

    comment = TaskComment.objects.create(task=task, user=user, content=content.strip())
    log_activity(
        user,
        "task_commented",
        f"{user.get_display_name()} vừa bình luận trong {task.code}.",
        project=task.project,
        task=task,
    )
    notify_users(
        _assignee_users(task) + [task.created_by],
        Notification.Type.TASK_COMMENT,
        "Bình luận mới",
        f"{user.get_display_name()} vừa bình luận trong {task.code}.",
        task.get_absolute_url(),
        exclude_user=user,
    )
    return comment


@transaction.atomic
def save_document(uploaded_file, uploaded_by, project=None, task=None):
    if task:
        task = locked_task(task)
        if project and project.pk != task.project_id:
            raise ValidationError("Tài liệu và công việc phải thuộc cùng dự án.")
        project = task.project
    elif project:
        project = lock_project(project.pk)
    if project:
        if project.archived_at or not can_view_project(uploaded_by, project):
            raise PermissionDenied("Dự án đang ở chế độ chỉ xem.")
    try:
        validate_upload_file(uploaded_file)
    except ValidationError:
        logger.warning("Rejected upload by user=%s name=%s", uploaded_by, uploaded_file.name)
        raise
    name, ext = os.path.splitext(uploaded_file.name)
    document = Document(
        name=name[:255],
        file=uploaded_file,
        original_name=uploaded_file.name[:255],
        file_type=ext.lower().lstrip("."),
        file_size=uploaded_file.size,
        project=project or (task.project if task else None),
        task=task,
        uploaded_by=uploaded_by,
    )
    document.save()
    log_activity(
        uploaded_by,
        "document_uploaded",
        f"{uploaded_by.get_display_name()} upload {document.original_name}.",
        project=document.project,
        task=task,
    )
    return document


def get_status_by_slug(slug):
    return Status.objects.get(scope="TASK", slug=slug)
