import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Department
from activity.models import ActivityLog
from activity.services import log_activity
from core.permissions import (
    can_create_project,
    can_edit_project_settings,
    can_manage_project,
    can_remove_member,
    can_view_project,
    is_admin,
)
from core.utils import safe_int
from core.models import Priority, Status
from notifications.models import Notification
from notifications.services import notify_users
from projects.forms import ProjectForm, ProjectMemberForm
from projects.models import Project, ProjectMember
from projects.services import (
    add_project_member, change_member_role, change_project_lifecycle, create_project,
    lock_managed_project, project_has_work, remove_project_member, transfer_owner,
)
from core.models import Priority as TaskPriority
from tasks.models import Document
from tasks.services import save_document
from tasks.workflow import kanban_columns, workflow_configuration

logger = logging.getLogger("taskflow")


def _project_queryset(user):
    qs = Project.objects.with_current().select_related("owner", "department").prefetch_related("members__user")
    if is_admin(user):
        return qs
    return qs.filter(members__user=user).distinct()


def _require_view(user, project):
    if not can_view_project(user, project):
        raise PermissionDenied("Bạn không có quyền xem dự án này.")


def _require_manage(user, project):
    if not can_manage_project(user, project):
        raise PermissionDenied("Bạn không có quyền quản lý dự án này.")


@login_required
def project_list(request):
    qs = _project_queryset(request.user).annotate(
        task_count=Count("tasks", filter=Q(tasks__is_deleted=False), distinct=True)
    )
    lifecycle = request.GET.get("lifecycle", "active")
    if lifecycle != "all":
        qs = qs.filter(archived_at__isnull=lifecycle != "archived")
    query = (request.GET.get("q") or "").strip()
    status_id = request.GET.get("status")
    priority_id = request.GET.get("priority")
    manager_id = request.GET.get("manager")
    department_id = safe_int(request.GET.get("department"))
    sort = request.GET.get("sort") or "-created_at"
    view_mode = request.GET.get("view") or "grid"
    allowed_sort = {
        "-created_at",
        "name",
        "-name",
        "end_date",
        "-end_date",
        "current_priority_order",
        "current_status_order",
        "created_at",
    }
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(description__icontains=query))
    if safe_int(status_id):
        qs = qs.filter(current_status_id=status_id)
    if safe_int(priority_id):
        qs = qs.filter(current_priority_id=priority_id)
    if safe_int(manager_id):
        qs = qs.filter(Q(owner_id=manager_id) | Q(members__user_id=manager_id, members__role__in=["OWNER", "MANAGER"]))
        qs = qs.distinct()
    if department_id:
        qs = qs.filter(department_id=department_id)
    if sort in allowed_sort:
        qs = qs.order_by(sort)
    page_size = min(max(safe_int(request.GET.get("page_size"), 12), 1), 100)
    page = Paginator(qs, page_size).get_page(request.GET.get("page"))
    managers = (
        _project_queryset(request.user)
        .values("owner_id", "owner__first_name", "owner__username")
        .distinct()
    )
    return render(
        request,
        "projects/list.html",
        {
            "page": page,
            "query": query,
            "status_id": status_id,
            "priority_id": priority_id,
            "manager_id": manager_id,
            "sort": sort,
            "view_mode": view_mode,
            "lifecycle": lifecycle,
            "statuses": Status.objects.filter(scope="PROJECT"),
            "priorities": Priority.objects.filter(scope="PROJECT"),
            "managers": managers,
            "can_create": can_create_project(request.user),
            "department_id": department_id,
            "departments": Department.objects.filter(pk__in=_project_queryset(request.user).order_by().values("department_id")),
        },
    )


@login_required
def project_create(request):
    if not can_create_project(request.user):
        raise PermissionDenied("Bạn không có quyền tạo dự án.")
    form = ProjectForm(request.POST or None, request.FILES or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            project = create_project(request.user, form.cleaned_data, form.cleaned_data.get("cover_image"))
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Tạo dự án thành công.")
            return redirect(project.get_absolute_url())
    return render(request, "projects/form.html", {"form": form, "title": "Tạo dự án"})


@login_required
@transaction.atomic
def project_edit(request, project_id):
    project = (lock_managed_project(project_id, request.user) if request.method == "POST"
               else get_object_or_404(Project, pk=project_id))
    _require_manage(request.user, project)
    old_name = project.name
    form = ProjectForm(request.POST or None, request.FILES or None, instance=project, actor=request.user)
    if request.method == "POST" and form.is_valid():
        project = form.save()
        log_activity(
            request.user,
            "project_updated",
            f"{request.user.get_display_name()} cập nhật dự án {project.name}.",
            project=project,
            old_value=old_name,
            new_value=project.name,
        )
        notify_users(
            [m.user for m in project.members.select_related("user")],
            Notification.Type.PROJECT_UPDATED,
            "Dự án được cập nhật",
            f"{project.name} vừa được cập nhật.",
            project.get_absolute_url(),
            exclude_user=request.user,
        )
        messages.success(request, "Cập nhật dự án thành công.")
        return redirect("projects:settings", project_id=project.pk)
    return render(request, "projects/form.html", {"form": form, "title": "Cập nhật dự án", "project": project})


@login_required
@require_POST
def project_lifecycle(request, project_id, action):
    project = get_object_or_404(Project, pk=project_id)
    if not can_edit_project_settings(request.user, project):
        raise PermissionDenied("Chỉ Owner hoặc Admin mới thay đổi vòng đời dự án.")
    if action == "delete" and request.POST.get("code", "").strip() != project.code:
        messages.error(request, "Nhập đúng mã dự án để xác nhận xóa.")
        return redirect("projects:settings", project_id=project.pk)
    try:
        change_project_lifecycle(project.pk, request.user, action)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, {
            "archive": "Đã lưu trữ dự án ở chế độ chỉ xem.",
            "restore": "Dự án đã hoạt động trở lại.",
            "delete": "Đã xóa dự án trống.",
        }[action])
    if action == "delete" and not Project.objects.filter(pk=project_id).exists():
        return redirect("projects:list")
    return redirect("projects:settings", project_id=project.pk)


def _detail_context(request, project, tab):
    stats = project.task_stats()
    membership = project.members.filter(user=request.user).first()
    return {
        "project": project,
        "tab": tab,
        "stats": stats,
        "can_manage": can_manage_project(request.user, project),
        "can_settings": can_edit_project_settings(request.user, project),
        "membership": membership,
        "members": project.members.select_related("user").order_by("role", "joined_at"),
    }


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(
        Project.objects.with_current().select_related("owner"),
        pk=project_id,
    )
    _require_view(request.user, project)
    recent = ActivityLog.objects.filter(project=project).select_related("user")[:10]
    context = _detail_context(request, project, "overview")
    context["recent_activity"] = recent
    return render(request, "projects/detail_overview.html", context)


@login_required
def project_tasks(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_view(request.user, project)
    tasks = project.tasks.with_current().select_related("task_type", "created_by").prefetch_related("assignees")
    status_id = request.GET.get("status")
    priority_id = request.GET.get("priority")
    assignee_id = request.GET.get("assignee")
    type_id = request.GET.get("type")
    focus = request.GET.get("focus") or ("overdue" if request.GET.get("overdue") else "all")
    query = (request.GET.get("q") or "").strip()
    sort = request.GET.get("sort") or ("due_date" if focus in {"overdue", "due_soon"} else "-created_at")
    if query:
        tasks = tasks.filter(Q(title__icontains=query) | Q(code__icontains=query))
    if safe_int(status_id):
        tasks = tasks.filter(current_status_id=status_id)
    if safe_int(priority_id):
        tasks = tasks.filter(current_priority_id=priority_id)
    if safe_int(assignee_id):
        tasks = tasks.filter(assignments__user_id=assignee_id)
    if safe_int(type_id):
        tasks = tasks.filter(task_type_id=type_id)
    tasks = tasks.focused(focus, request.user)
    allowed = {"-created_at", "title", "-title", "due_date", "-due_date", "current_priority_order", "current_status_order"}
    if sort in allowed:
        tasks = tasks.order_by(sort)
    page_size = min(max(safe_int(request.GET.get("page_size"), 10), 1), 100)
    page = Paginator(tasks.distinct(), page_size).get_page(request.GET.get("page"))
    context = _detail_context(request, project, "tasks")
    _, statuses, _ = workflow_configuration(project)
    context.update({"page": page, "query": query, "sort": sort, "focus": focus, "statuses": statuses,
                    "priorities": TaskPriority.objects.filter(scope="TASK"), "task_types": project.task_types.all()})
    return render(request, "projects/detail_tasks.html", context)


@login_required
def project_kanban(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_view(request.user, project)
    context = _detail_context(request, project, "kanban")
    context["columns"] = kanban_columns(project, request.user)
    return render(request, "projects/detail_kanban.html", context)


@login_required
def project_members(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_view(request.user, project)
    form = ProjectMemberForm(project=project)
    query = (request.GET.get("q") or "").strip()
    members = project.members.select_related("user", "added_by")
    if query:
        members = members.filter(
            Q(user__first_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
        )
    context = _detail_context(request, project, "members")
    context.update({"form": form, "filtered_members": members, "query": query})
    return render(request, "projects/detail_members.html", context)


@login_required
@require_POST
def member_add(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_manage(request.user, project)
    form = ProjectMemberForm(request.POST, project=project)
    if form.is_valid():
        try:
            add_project_member(project, form.cleaned_data["user"], form.cleaned_data["role"], request.user)
            messages.success(request, "Đã thêm thành viên.")
        except ValueError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Hãy chọn một người đủ điều kiện và chưa thuộc dự án.")
    return redirect("projects:members", project_id=project.pk)


@login_required
@require_POST
def member_remove(request, project_id, member_id):
    project = get_object_or_404(Project, pk=project_id)
    member = get_object_or_404(ProjectMember, pk=member_id, project=project)
    if not can_remove_member(request.user, project, member):
        raise PermissionDenied("Không thể xóa thành viên này.")
    try:
        remove_project_member(project, member, request.user)
        messages.success(request, "Đã xóa thành viên.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("projects:members", project_id=project.pk)


@login_required
@require_POST
def member_role(request, project_id, member_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_manage(request.user, project)
    member = get_object_or_404(ProjectMember, pk=member_id, project=project)
    role = request.POST.get("role")
    if role not in dict(ProjectMember.Role.choices):
        messages.error(request, "Vai trò không hợp lệ.")
        return redirect("projects:members", project_id=project.pk)
    try:
        change_member_role(project, member, role, request.user)
        messages.success(request, "Đã đổi vai trò thành viên.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("projects:members", project_id=project.pk)


@login_required
def project_documents(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_view(request.user, project)
    documents = Document.objects.filter(project=project, is_deleted=False)
    query = (request.GET.get("q") or "").strip()
    file_type = request.GET.get("type")
    if query:
        documents = documents.filter(Q(name__icontains=query) | Q(original_name__icontains=query))
    if file_type:
        documents = documents.filter(file_type=file_type)
    if request.method == "POST":
        if project.archived_at:
            raise PermissionDenied("Dự án lưu trữ chỉ cho phép xem tài liệu.")
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "Hãy chọn tệp để tải lên.")
        else:
            try:
                save_document(uploaded, request.user, project=project)
                messages.success(request, "Tải tài liệu thành công.")
                return redirect("projects:documents", project_id=project.pk)
            except ValidationError as exc:
                logger.warning("File upload rejected: %s", exc)
                messages.error(request, "Không thể tải tệp. Kiểm tra định dạng và dung lượng.")
            except Exception:
                logger.exception("File error while uploading project document")
                messages.error(request, "Có lỗi khi lưu tệp. Vui lòng thử lại.")
    context = _detail_context(request, project, "documents")
    context.update({"documents": documents, "query": query, "file_type": file_type})
    return render(request, "projects/detail_documents.html", context)


@login_required
def project_activity(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_view(request.user, project)
    logs = ActivityLog.objects.filter(project=project).select_related("user", "task")
    page = Paginator(logs, 20).get_page(request.GET.get("page"))
    context = _detail_context(request, project, "activity")
    context["page"] = page
    return render(request, "projects/detail_activity.html", context)


@login_required
def project_settings(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_view(request.user, project)
    form = ProjectForm(instance=project)
    context = _detail_context(request, project, "settings")
    context.update({"form": form, "has_work": project_has_work(project)})
    return render(request, "projects/detail_settings.html", context)


@login_required
@require_POST
def project_transfer_owner(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not can_edit_project_settings(request.user, project) and not is_admin(request.user):
        raise PermissionDenied("Chỉ Owner hoặc Admin mới chuyển quyền sở hữu.")
    member = get_object_or_404(ProjectMember, pk=request.POST.get("member_id"), project=project)
    transfer_owner(project, member.user, request.user)
    messages.success(request, "Đã chuyển quyền sở hữu dự án.")
    return redirect("projects:settings", project_id=project.pk)
