from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from activity.services import log_activity
from core.models import Status
from core.permissions import can_manage_project, get_membership
from projects.models import ProjectMember
from projects.services import lock_managed_project
from tasks.models import CLOSED_STAGES, TaskTransition, TaskWorkflow

Stage = Status.Stage
Role = TaskTransition.Role

DEFAULT_TRANSITIONS = {
    Stage.TODO: (Stage.ACTIVE, Stage.PAUSED, Stage.DELAYED),
    Stage.ACTIVE: (Stage.PAUSED, Stage.DELAYED, Stage.REVIEW),
    Stage.PAUSED: (Stage.ACTIVE, Stage.DELAYED),
    Stage.DELAYED: (Stage.ACTIVE, Stage.PAUSED, Stage.REVIEW),
    Stage.REWORK: (Stage.ACTIVE, Stage.PAUSED, Stage.DELAYED, Stage.REVIEW),
    Stage.REVIEW: (Stage.COMPLETED, Stage.REJECTED, Stage.REWORK),
    Stage.COMPLETED: (Stage.REWORK,),
    Stage.REJECTED: (Stage.REWORK,),
}


def available_statuses(project):
    return Status.objects.filter(scope="TASK").filter(Q(project__isnull=True) | Q(project=project))


def workflow_configuration(project):
    workflow = TaskWorkflow.objects.filter(project=project).first()
    if workflow:
        return (
            workflow.initial_status_id,
            list(workflow.statuses.all()),
            list(workflow.transitions.values_list("source_id", "target_id", "role")),
        )
    statuses = list(Status.objects.filter(scope="TASK", project__isnull=True).filter(
        ~Q(slug="blocked") | Q(pk__in=project.tasks.with_current().order_by().values("current_status_id"))
    ))
    initial = next((status.pk for status in statuses if status.slug == Stage.TODO), None)
    transitions = [
        (source.pk, target.pk, role)
        for source in statuses
        for target in statuses
        if target.stage in DEFAULT_TRANSITIONS.get(source.stage, ()) and source.pk != target.pk
        for role in permitted_roles(source, target)
    ]
    return initial, statuses, transitions


def permitted_roles(source, target):
    if target.stage in CLOSED_STAGES:
        return (Role.MANAGER,) if source.stage == Stage.REVIEW else ()
    if source.stage in CLOSED_STAGES or source.stage == Stage.REVIEW:
        return (Role.MANAGER,) if target.stage == Stage.REWORK else ()
    if target.stage == Stage.REVIEW:
        return (Role.ASSIGNEE,)
    return (Role.MANAGER, Role.ASSIGNEE)


def initial_status(project):
    workflow = TaskWorkflow.objects.filter(project=project).select_related("initial_status").first()
    if workflow:
        return workflow.initial_status
    return Status.objects.get(scope="TASK", project__isnull=True, slug=Stage.TODO)


def workflow_actor(user, project):
    membership = get_membership(user, project)
    return (
        can_manage_project(user, project),
        bool(not project.archived_at and not project.is_deleted and membership
             and membership.role != ProjectMember.Role.VIEWER
             and (not project.department_id or user.department_id == project.department_id)),
    )


def allowed_targets(task, user, statuses, transitions, actor):
    manager, can_be_assignee = actor
    assignee = can_be_assignee and any(assignment.user_id == user.pk for assignment in task.assignments.all())
    roles = {role for role, allowed in ((Role.MANAGER, manager), (Role.ASSIGNEE, assignee)) if allowed}
    target_roles = {(target, role) for source, target, role in transitions if source == task.status_id and role in roles}
    return [status for status in statuses if any(
        (status.pk, role) in target_roles for role in permitted_roles(task.status, status)
    )]


def kanban_columns(project, user):
    _, statuses, transitions = workflow_configuration(project)
    columns = {status.pk: {"status": status, "tasks": []} for status in statuses}
    actor = workflow_actor(user, project)
    tasks = project.tasks.with_current().select_related("task_type").prefetch_related(
        "assignees", "assignments", "comments", "documents"
    )
    for task in tasks:
        targets = allowed_targets(task, user, statuses, transitions, actor)
        task.transition_ids = ",".join(str(status.pk) for status in targets)
        columns.setdefault(task.status_id, {"status": task.status, "tasks": []})["tasks"].append(task)
    return list(columns.values())


def validate_configuration(project, initial, statuses, rules):
    by_id = {status.pk: status for status in statuses}
    if initial.pk not in by_id or initial.stage != Stage.TODO:
        raise ValidationError("Trạng thái khởi đầu phải được bật và thuộc giai đoạn Mới.")
    if any(status.project_id not in (None, project.pk) for status in statuses):
        raise ValidationError("Chỉ dùng trạng thái chung hoặc của dự án này.")
    if project.tasks.with_current().exclude(current_status_id__in=by_id).exists():
        raise ValidationError("Hãy chuyển các công việc hiện có trước khi bỏ trạng thái của chúng.")
    if len(rules) != len(set(rules)):
        raise ValidationError("Có luật chuyển bị trùng.")
    for source_id, target_id, role in rules:
        source, target = by_id.get(source_id), by_id.get(target_id)
        if not source or not target or source == target:
            raise ValidationError("Mỗi luật phải nối hai trạng thái đang bật và khác nhau.")
        if role not in permitted_roles(source, target):
            raise ValidationError(f"Vai trò đã chọn không được chuyển từ {source.name} sang {target.name}.")


@transaction.atomic
def save_configuration(project, actor, initial, statuses, rules):
    project = lock_managed_project(project.pk, actor)
    validate_configuration(project, initial, statuses, rules)
    workflow, _ = TaskWorkflow.objects.update_or_create(project=project, defaults={"initial_status": initial})
    workflow.statuses.set(statuses)
    workflow.transitions.all().delete()
    TaskTransition.objects.bulk_create([
        TaskTransition(workflow=workflow, source_id=source, target_id=target, role=role)
        for source, target, role in rules
    ])
    log_activity(actor, "task_workflow_updated", f"Cập nhật luồng công việc của {project.code}.", project=project)
