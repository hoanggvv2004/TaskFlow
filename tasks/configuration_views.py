from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from activity.services import log_activity
from core.permissions import can_manage_project
from core.utils import safe_int
from projects.models import Project
from projects.services import lock_managed_project
from projects.views import _detail_context
from tasks.forms import StatusForm, TaskTypeForm, TransitionFormSet, WorkflowForm
from tasks.models import TaskType
from tasks.workflow import available_statuses, save_configuration, workflow_configuration


@login_required
def project_workflow(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("Chỉ quản lý mới được cấu hình luồng công việc.")

    initial, statuses, transitions = workflow_configuration(project)
    action = request.POST.get("action")
    status_id = safe_int(request.POST.get("status_id") if action == "status" else request.GET.get("status"))
    type_id = safe_int(request.POST.get("type_id") if action == "type" else request.GET.get("type"))
    edit_status = get_object_or_404(project.custom_task_statuses, pk=status_id) if status_id else None
    edit_type = get_object_or_404(project.task_types, pk=type_id) if type_id else None
    form = WorkflowForm(
        request.POST if action == "workflow" else None, project=project,
        initial={"initial": initial, "statuses": [status.pk for status in statuses]},
    )
    rules = TransitionFormSet(
        request.POST if action == "workflow" else None,
        initial=[{"source": source, "target": target, "role": role} for source, target, role in transitions],
        form_kwargs={"project": project},
    )
    status_form = StatusForm(request.POST if action == "status" else None,
                             instance=edit_status, initial=None if edit_status else {"color": "#6B7280", "sort_order": 10})
    type_form = TaskTypeForm(request.POST if action == "type" else None, instance=edit_type)

    if action == "workflow" and form.is_valid() and rules.is_valid():
        rule_rows = [
            (row["source"].pk, row["target"].pk, row["role"])
            for row in rules.cleaned_data if row and not row.get("DELETE")
        ]
        try:
            save_configuration(project, request.user, form.cleaned_data["initial"],
                               form.cleaned_data["statuses"], rule_rows)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Đã lưu trạng thái và luật chuyển của dự án.")
            return redirect("projects:workflow", project_id=project.pk)

    if action == "status" and status_form.is_valid():
        with transaction.atomic():
            project = lock_managed_project(project.pk, request.user)
            status = status_form.save(commit=False)
            status.project = project
            status.scope = "TASK"
            if available_statuses(project).filter(name=status.name).exclude(pk=status.pk).exists():
                status_form.add_error("name", "Đã có trạng thái khả dụng mang tên này.")
            else:
                if edit_status:
                    status.save(update_fields=["name", "color", "sort_order"])
                    messages.success(request, "Đã cập nhật cột trạng thái.")
                else:
                    status.slug = f"custom-{uuid4().hex}"
                    status.save()
                    messages.success(request, "Đã tạo cột. Chọn cột và thêm luật chuyển để đưa vào luồng.")
                log_activity(request.user, "task_status_configured", f"Cập nhật cột {status.name}.", project=project)
                return redirect("projects:workflow", project_id=project.pk)

    if action == "type" and type_form.is_valid():
        with transaction.atomic():
            project = lock_managed_project(project.pk, request.user)
            task_type = type_form.save(commit=False)
            task_type.project = project
            if project.task_types.filter(name=task_type.name).exclude(pk=task_type.pk).exists():
                type_form.add_error("name", "Dự án đã có loại công việc mang tên này.")
            else:
                task_type.save(update_fields=["name"] if edit_type else None)
                messages.success(request, f"Đã lưu loại công việc {task_type.name}.")
                return redirect("projects:workflow", project_id=project.pk)

    if action == "toggle_type":
        with transaction.atomic():
            project = lock_managed_project(project.pk, request.user)
            task_type = get_object_or_404(TaskType, project=project, pk=request.POST.get("type_id"))
            task_type.is_active = request.POST.get("active") == "1"
            task_type.save(update_fields=["is_active"])
            messages.success(request, "Đã cập nhật loại công việc.")
            return redirect("projects:workflow", project_id=project.pk)

    context = _detail_context(request, project, "settings")
    context.update({"form": form, "rules": rules, "status_form": status_form,
                    "type_form": type_form, "task_types": project.task_types.all(),
                    "custom_statuses": project.custom_task_statuses.all(), "edit_status": edit_status, "edit_type": edit_type})
    return render(request, "projects/workflow.html", context)
