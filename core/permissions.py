from accounts.models import Department, User
from projects.models import ProjectMember


def is_admin(user):
    return bool(user and user.is_authenticated and (user.role == User.Role.ADMIN or user.is_superuser))


def is_project_manager_role(user):
    return bool(user and user.is_authenticated and user.role == User.Role.PROJECT_MANAGER)


def is_department_head(user):
    return bool(user and user.is_authenticated and user.department_id and user.department.manager_id == user.pk)


def can_view_own_department(user):
    return is_project_manager_role(user) or is_department_head(user)


def get_membership(user, project):
    if not user or not user.is_authenticated:
        return None
    return (
        ProjectMember.objects.select_related("user", "project")
        .filter(project=project, user=user)
        .first()
    )


def can_view_project(user, project):
    if project.is_deleted:
        return False
    if is_admin(user):
        return True
    return get_membership(user, project) is not None


def can_manage_project(user, project):
    if project.is_deleted or project.archived_at:
        return False
    if is_admin(user):
        return True
    membership = get_membership(user, project)
    if not membership:
        return False
    return membership.role in {ProjectMember.Role.OWNER, ProjectMember.Role.MANAGER}


def can_edit_project_settings(user, project):
    if project.is_deleted:
        return False
    if is_admin(user):
        return True
    membership = get_membership(user, project)
    return bool(membership and membership.role == ProjectMember.Role.OWNER)


def can_create_project(user):
    if is_admin(user):
        return True
    if not user or not user.is_authenticated:
        return False
    if user.department_id:
        return Department.objects.filter(pk=user.department_id, manager=user, is_active=True).exists()
    return is_project_manager_role(user)


def can_manage_task(user, task):
    return can_manage_project(user, task.project)


def can_update_task(user, task):
    return can_manage_task(user, task) or is_task_assignee(user, task)


def is_task_assignee(user, task):
    if task.is_deleted or task.project.is_deleted or task.project.archived_at:
        return False
    membership = get_membership(user, task.project)
    if not membership or membership.role == ProjectMember.Role.VIEWER:
        return False
    if task.project.department_id and user.department_id != task.project.department_id:
        return False
    return task.assignments.filter(user=user).exists()


def can_comment_task(user, task):
    if task.is_deleted or task.project.is_deleted or task.project.archived_at:
        return False
    if is_admin(user):
        return True
    membership = get_membership(user, task.project)
    return bool(membership and membership.role != ProjectMember.Role.VIEWER)


def can_view_task(user, task):
    return can_view_project(user, task.project)


def can_assign_task(user, task):
    return can_manage_project(user, task.project)


def can_delete_task(user, task):
    return can_manage_project(user, task.project)


def can_manage_members(user, project):
    return can_manage_project(user, project)


def can_remove_member(user, project, target_member):
    if not can_manage_members(user, project):
        return False
    if target_member.role == ProjectMember.Role.OWNER:
        return False
    return True
