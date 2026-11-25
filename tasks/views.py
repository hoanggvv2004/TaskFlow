import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.permissions import (
    can_comment_task,
    can_manage_project,
    can_update_task,
    can_view_project,
    can_view_task,
    is_admin,
)
from core.models import Priority, Status
from core.utils import safe_int
from projects.models import Project
from projects.services import lock_project
from tasks.forms import ChecklistForm, CommentForm, QuickTaskForm, TaskForm
from tasks.models import Document, Task, TaskChecklist, TaskComment
from tasks.services import add_comment, create_task, delete_task, edit_task, locked_task, save_document, update_task_status
from tasks.workflow import allowed_targets, kanban_columns, workflow_actor, workflow_configuration

logger = logging.getLogger("taskflow")


def _json_error(message, status=400):
    return JsonResponse({"success": False, "message": message}, status=status)


def _visible_tasks(user):
    qs = Task.objects.with_current().select_related("project", "created_by").prefetch_related("assignees")
    if is_admin(user):
        return qs
    return qs.filter(project__members__user=user).distinct()


@login_required
def task_list(request):
    qs = _visible_tasks(request.user)
    query = (request.GET.get("q") or "").strip()
    project_id = request.GET.get("project")
    status_id = request.GET.get("status")
    priority_id = request.GET.get("priority")
    assignee_id = request.GET.get("assignee")
    due = request.GET.get("due")
    overdue = request.GET.get("overdue")
    sort = request.GET.get("sort") or "-created_at"
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(code__icontains=query) | Q(description__icontains=query))
    if safe_int(project_id):
        qs = qs.filter(project_id=project_id)
    else:
        qs = qs.filter(project__archived_at__isnull=True)
    statuses = Status.objects.filter(scope="TASK", pk__in=qs.order_by().values("current_status_id"))
    if safe_int(status_id):
        qs = qs.filter(current_status_id=status_id)
    if safe_int(priority_id):
        qs = qs.filter(current_priority_id=priority_id)
    if safe_int(assignee_id):
        qs = qs.filter(assignments__user_id=assignee_id)
    if due:
        qs = qs.filter(due_date=due)
    allowed = {"-created_at", "title", "due_date", "-due_date", "current_priority_order", "current_status_order", "created_at"}
    if sort in allowed:
        qs = qs.order_by(sort)
    if sort == "current_priority_order":
        qs = qs.order_by("current_priority_order")
    if sort == "current_status_order":
        qs = qs.order_by("current_status_order")
    if overdue:
        qs = qs.overdue()
    page_size = min(max(safe_int(request.GET.get("page_size"), 10), 1), 100)
    page = Paginator(qs.distinct(), page_size).get_page(request.GET.get("page"))
    projects = Project.objects.filter(members__user=request.user) if not is_admin(request.user) else Project.objects.all()
    return render(
        request,
        "tasks/list.html",
        {
            "page": page,
            "query": query,
            "statuses": statuses,
            "priorities": Priority.objects.filter(scope="TASK"),
            "projects": projects,
            "project_id": project_id,
            "status_id": status_id,
            "priority_id": priority_id,
            "assignee_id": assignee_id,
            "sort": sort,
            "overdue": overdue,
        },
    )


@login_required
def my_tasks(request):
    qs = (
        _visible_tasks(request.user).filter(assignments__user=request.user, project__archived_at__isnull=True)
        .with_current()
        .select_related("project")
        .prefetch_related("assignees")
        .distinct()
    )
    status_id = request.GET.get("status")
    statuses = Status.objects.filter(scope="TASK", pk__in=qs.order_by().values("current_status_id"))
    if safe_int(status_id):
        qs = qs.filter(current_status_id=status_id)
    page = Paginator(qs.order_by("due_date", "-created_at"), 10).get_page(request.GET.get("page"))
    return render(request, "tasks/my_tasks.html", {"page": page, "statuses": statuses})


@login_required
def task_create(request):
    project_id = safe_int(request.GET.get("project") or request.POST.get("project"))
    project = get_object_or_404(Project, pk=project_id) if project_id else None
    if project and not can_manage_project(request.user, project) and not can_view_project(request.user, project):
        raise PermissionDenied("Bạn không thuộc dự án này.")
    if project and not can_manage_project(request.user, project):
        raise PermissionDenied("Chỉ quản lý dự án mới được tạo nhiệm vụ.")
    if not project:
        projects = Project.objects.filter(archived_at__isnull=True)
        if not is_admin(request.user):
            projects = projects.filter(members__user=request.user, members__role__in=["OWNER", "MANAGER"])
        return render(request, "tasks/select_project.html", {"projects": projects})
    form = TaskForm(request.POST or None, project=project)
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k not in {"assignees", "confirm_outside_deadline"}}
        try:
            task = create_task(
                request.user,
                project,
                data,
                form.assignee_user_ids(),
                warn_deadline=form.cleaned_data.get("confirm_outside_deadline"),
            )
            messages.success(request, "Tạo nhiệm vụ thành công.")
            return redirect(task.get_absolute_url())
        except ValidationError as exc:
            form.add_error(None, exc.messages)
    return render(request, "tasks/form.html", {"form": form, "project": project, "title": "Tạo nhiệm vụ"})


@login_required
def task_edit(request, task_id):
    task = get_object_or_404(Task.objects.with_current().select_related("project"), pk=task_id)
    if not can_manage_project(request.user, task.project):
        raise PermissionDenied("Bạn không có quyền sửa nhiệm vụ này.")
    form = TaskForm(request.POST or None, instance=task, project=task.project)
    if request.method == "POST" and form.is_valid():
        try:
            task = edit_task(task, request.user, form.cleaned_data, form.assignee_user_ids(),
                             confirm_outside=form.cleaned_data["confirm_outside_deadline"])
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Cập nhật nhiệm vụ thành công.")
            return redirect(task.get_absolute_url())
    return render(request, "tasks/form.html", {"form": form, "project": task.project, "task": task, "title": "Sửa nhiệm vụ"})


@login_required
@require_POST
def task_delete(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    project_id = task.project_id
    delete_task(task, request.user)
    messages.success(request, "Đã lưu trữ nhiệm vụ.")
    return redirect("projects:tasks", project_id=project_id)


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(
        Task.objects.with_current().select_related("project", "task_type", "created_by").prefetch_related(
            "assignees", "assignments", "comments__user", "checklist_items", "documents",
            "history__user", "history__old_status", "history__new_status"
        ),
        pk=task_id,
    )
    if not can_view_task(request.user, task):
        raise PermissionDenied("Bạn không có quyền xem nhiệm vụ này.")
    _, statuses, rules = workflow_configuration(task.project)
    return render(
        request,
        "tasks/detail.html",
        {
            "task": task,
            "comment_form": CommentForm(),
            "checklist_form": ChecklistForm(),
            "can_manage": can_manage_project(request.user, task.project),
            "can_update": can_update_task(request.user, task),
            "can_comment": can_comment_task(request.user, task),
            "statuses": allowed_targets(task, request.user, statuses, rules, workflow_actor(request.user, task.project)),
        },
    )


@login_required
@require_POST
def ajax_status(request, task_id):
    task = get_object_or_404(Task.objects.with_current().select_related("project"), pk=task_id)
    payload = request.POST
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return _json_error("Dữ liệu không hợp lệ.")
    if not hasattr(payload, "get"):
        return _json_error("Dữ liệu không hợp lệ.")
    status_id = safe_int(payload.get("status_id") or payload.get("status"))
    if not can_update_task(request.user, task):
        return _json_error("Bạn không có quyền đổi trạng thái nhiệm vụ.", 403)
    status = Status.objects.filter(scope="TASK", pk=status_id).first()
    if not status:
        return _json_error("Trạng thái không hợp lệ.")
    try:
        task = update_task_status(task, status, request.user, str(payload.get("note") or "").strip(),
                                  expected_status_id=safe_int(payload.get("source_id")) or None)
    except PermissionDenied as exc:
        return _json_error(str(exc), 403)
    except ValidationError as exc:
        return _json_error(exc.messages[0])
    _, statuses, rules = workflow_configuration(task.project)
    targets = allowed_targets(task, request.user, statuses, rules, workflow_actor(request.user, task.project))
    return JsonResponse(
        {
            "success": True,
            "message": "Cập nhật trạng thái thành công.",
            "status": {"id": task.status.id, "name": task.status.name, "slug": task.status.stage},
            "targets": [target.pk for target in targets],
            "progress": task.progress,
        }
    )


@login_required
@require_POST
@transaction.atomic
def ajax_comment_add(request, task_id):
    task = locked_task(get_object_or_404(Task, pk=task_id))
    if not can_comment_task(request.user, task):
        return _json_error("Bạn không có quyền bình luận.", 403)
    content = (request.POST.get("content") or "").strip()
    if not content:
        return _json_error("Nội dung bình luận không được trống.")
    comment = add_comment(task, request.user, content)
    return JsonResponse(
        {
            "success": True,
            "message": "Đã thêm bình luận.",
            "comment": {
                "id": comment.id,
                "content": comment.content,
                "author": comment.user.get_display_name(),
                "initials": comment.user.get_initials(),
                "created_at": comment.created_at.strftime("%d/%m/%Y %H:%M"),
                "avatar": comment.user.avatar.url if comment.user.avatar else "",
            },
        }
    )


@login_required
@require_POST
@transaction.atomic
def ajax_comment_edit(request, comment_id):
    comment = get_object_or_404(TaskComment, pk=comment_id)
    task = locked_task(comment.task)
    if not can_comment_task(request.user, task) or (comment.user_id != request.user.id and not is_admin(request.user)):
        return _json_error("Bạn chỉ sửa được bình luận của mình.", 403)
    content = (request.POST.get("content") or "").strip()
    if not content:
        return _json_error("Nội dung không được trống.")
    comment.content = content
    comment.save(update_fields=["content", "updated_at"])
    return JsonResponse({"success": True, "message": "Đã cập nhật bình luận.", "content": comment.content})


@login_required
@require_POST
@transaction.atomic
def ajax_comment_delete(request, comment_id):
    comment = get_object_or_404(TaskComment, pk=comment_id)
    task = locked_task(comment.task)
    if not can_comment_task(request.user, task) or (comment.user_id != request.user.id and not is_admin(request.user)):
        return _json_error("Bạn chỉ xóa được bình luận của mình.", 403)
    comment.delete()
    return JsonResponse({"success": True, "message": "Đã xóa bình luận."})


@login_required
@require_POST
@transaction.atomic
def ajax_checklist_add(request, task_id):
    task = locked_task(get_object_or_404(Task, pk=task_id))
    if not can_update_task(request.user, task):
        return _json_error("Bạn không có quyền thêm checklist.", 403)
    title = (request.POST.get("title") or "").strip()
    if not title:
        return _json_error("Hãy nhập nội dung hạng mục.")
    item = TaskChecklist.objects.create(task=task, title=title, created_by=request.user)
    return JsonResponse({
        "success": True, "id": item.id, "title": item.title, "is_completed": item.is_completed,
        "html": render_to_string("tasks/checklist_item.html", {"item": item, "can_update": True}),
    })


@login_required
@require_POST
@transaction.atomic
def ajax_checklist_toggle(request, item_id):
    item = get_object_or_404(TaskChecklist.objects.select_related("task__project"), pk=item_id)
    task = locked_task(item.task)
    if not can_update_task(request.user, task):
        return _json_error("Bạn không có quyền cập nhật checklist.", 403)
    item = get_object_or_404(TaskChecklist.objects.select_for_update(), pk=item_id, task=task)
    item.is_completed = not item.is_completed
    item.save(update_fields=["is_completed"])
    return JsonResponse({"success": True, "is_completed": item.is_completed})


@login_required
@require_POST
@transaction.atomic
def ajax_checklist_delete(request, item_id):
    item = get_object_or_404(TaskChecklist.objects.select_related("task__project"), pk=item_id)
    task = locked_task(item.task)
    if not can_update_task(request.user, task):
        return _json_error("Bạn không có quyền xóa hạng mục checklist.", 403)
    item = get_object_or_404(TaskChecklist.objects.select_for_update(), pk=item_id, task=task)
    item.delete()
    return JsonResponse({"success": True, "message": "Đã xóa hạng mục checklist."})


@login_required
@require_POST
def ajax_document_upload(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    if not can_comment_task(request.user, task):
        return _json_error("Bạn không có quyền tải tệp.", 403)
    uploaded = request.FILES.get("file")
    if not uploaded:
        return _json_error("Hãy chọn tệp.")
    try:
        document = save_document(uploaded, request.user, project=task.project, task=task)
    except PermissionDenied as exc:
        return _json_error(str(exc), 403)
    except ValidationError as exc:
        return _json_error(exc.messages[0] if getattr(exc, "messages", None) else "Tệp không hợp lệ.")
    except Exception:
        logger.exception("File error uploading task attachment")
        return _json_error("Không thể lưu tệp.", 500)
    return JsonResponse(
        {
            "success": True,
            "message": "Tải tệp thành công.",
            "document": {
                "id": document.id,
                "name": document.original_name,
                "url": document.file.url,
            },
        }
    )


@login_required
def document_download(request, document_id):
    document = get_object_or_404(Document, pk=document_id, is_deleted=False)
    project = document.project or (document.task.project if document.task else None)
    if project and not can_view_project(request.user, project):
        raise PermissionDenied("Bạn không có quyền tải tệp này.")
    try:
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_name)
    except Exception:
        logger.exception("File error downloading document=%s", document_id)
        messages.error(request, "Không thể tải tệp.")
        return redirect("tasks:documents")


@login_required
@require_POST
@transaction.atomic
def document_delete(request, document_id):
    document = get_object_or_404(Document, pk=document_id, is_deleted=False)
    project = document.project or (document.task.project if document.task else None)
    if project:
        project = lock_project(project.pk)
        if project.archived_at or not can_view_project(request.user, project) or (
            not can_manage_project(request.user, project) and document.uploaded_by_id != request.user.id
        ):
            raise PermissionDenied("Bạn không có quyền xóa tệp này.")
    document.is_deleted = True
    document.save(update_fields=["is_deleted"])
    messages.success(request, "Đã xóa tài liệu.")
    next_url = request.POST.get("next") or "tasks:documents"
    if str(next_url).startswith("/"):
        return redirect(next_url)
    return redirect("tasks:documents")


@login_required
def document_list(request):
    docs = Document.objects.filter(is_deleted=False, project__is_deleted=False).select_related("project", "task", "uploaded_by")
    if not is_admin(request.user):
        docs = docs.filter(project__members__user=request.user).distinct()
    query = (request.GET.get("q") or "").strip()
    file_type = request.GET.get("type")
    project_id = request.GET.get("project")
    if query:
        docs = docs.filter(Q(name__icontains=query) | Q(original_name__icontains=query))
    if file_type:
        docs = docs.filter(file_type=file_type)
    if project_id:
        docs = docs.filter(project_id=project_id)
    else:
        docs = docs.filter(project__archived_at__isnull=True)
    page = Paginator(docs, 12).get_page(request.GET.get("page"))
    projects = Project.objects.filter(members__user=request.user) if not is_admin(request.user) else Project.objects.all()
    return render(request, "tasks/documents.html", {"page": page, "query": query, "file_type": file_type, "projects": projects})


@login_required
def global_kanban(request):
    project_id = request.GET.get("project")
    projects = Project.objects.filter(members__user=request.user) if not is_admin(request.user) else Project.objects.all()
    project = None
    if project_id:
        project = get_object_or_404(Project, pk=project_id)
        if not can_view_project(request.user, project):
            raise PermissionDenied("Bạn không thuộc dự án này.")
    else:
        project = projects.filter(archived_at__isnull=True).first()
    columns = kanban_columns(project, request.user) if project else []
    return render(
        request,
        "tasks/kanban.html",
        {"project": project, "projects": projects, "columns": columns, "can_manage": project and can_manage_project(request.user, project)},
    )


@login_required
def calendar_view(request):
    return render(request, "tasks/calendar.html")


@login_required
def calendar_events(request):
    start = parse_date((request.GET.get("start") or "")[:10])
    end = parse_date((request.GET.get("end") or "")[:10])
    projects = Project.objects.all() if is_admin(request.user) else Project.objects.filter(members__user=request.user)
    projects = projects.filter(archived_at__isnull=True)
    tasks = Task.objects.with_current().filter(project__in=projects).select_related("project")
    events = []
    for project in projects:
        if project.start_date:
            events.append(
                {
                    "id": f"p-start-{project.id}",
                    "title": f"{project.code} bắt đầu",
                    "start": project.start_date.isoformat(),
                    "url": project.get_absolute_url(),
                    "color": "#6366F1",
                }
            )
        if project.end_date:
            events.append(
                {
                    "id": f"p-end-{project.id}",
                    "title": f"{project.code} deadline",
                    "start": project.end_date.isoformat(),
                    "url": project.get_absolute_url(),
                    "color": "#7C3AED",
                }
            )
    for task in tasks:
        if task.start_date:
            events.append(
                {
                    "id": f"t-start-{task.id}",
                    "title": f"{task.code} start",
                    "start": task.start_date.isoformat(),
                    "url": task.get_absolute_url(),
                    "color": "#5B6CFF",
                }
            )
        if task.due_date:
            events.append(
                {
                    "id": f"t-due-{task.id}",
                    "title": f"{task.code} {task.title}",
                    "start": task.due_date.isoformat(),
                    "url": task.get_absolute_url(),
                    "color": "#F59E0B" if task.is_overdue else "#10B981",
                }
            )
    if start and end:
        events = [e for e in events if start.isoformat() <= e["start"] <= end.isoformat()]
    return JsonResponse(events, safe=False)


@login_required
@require_POST
def quick_create_task(request):
    project = get_object_or_404(Project, pk=safe_int(request.POST.get("project_id")))
    if not can_manage_project(request.user, project):
        raise PermissionDenied("Bạn không có quyền tạo nhiệm vụ.")
    form = QuickTaskForm(request.POST, project=project)
    if not form.is_valid():
        messages.error(request, "Kiểm tra tiêu đề, mức ưu tiên, loại và hạn công việc.")
        return redirect(project.get_absolute_url())
    confirm = request.POST.get("confirm_outside_deadline") == "on"
    try:
        task = create_task(
            request.user,
            project,
            {
                "title": form.cleaned_data["title"],
                "description": request.POST.get("description") or "",
                "priority": form.cleaned_data["priority_id"],
                "task_type": form.cleaned_data["task_type"],
                "due_date": form.cleaned_data["due_date"],
            },
            warn_deadline=confirm,
        )
        messages.success(request, f"Đã tạo {task.code}.")
        return redirect(task.get_absolute_url())
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if getattr(exc, "messages", None) else "Không thể tạo nhiệm vụ.")
        return redirect(project.get_absolute_url())
