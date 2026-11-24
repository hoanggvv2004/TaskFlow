import re

from django import forms
from django.db.models import Q

from core.models import Priority, Status
from projects.models import ProjectMember
from tasks.models import Task, TaskTransition, TaskType
from tasks.services import assignable_members
from tasks.workflow import available_statuses, initial_status


class DateInput(forms.DateInput):
    input_type = "date"


class TaskForm(forms.ModelForm):
    priority = forms.ModelChoiceField(
        queryset=Priority.objects.filter(scope="TASK"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Mức ưu tiên",
    )
    assignees = forms.ModelMultipleChoiceField(
        queryset=ProjectMember.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
        label="Người phụ trách",
    )
    confirm_outside_deadline = forms.BooleanField(
        required=False,
        label="Xác nhận hạn task ngoài deadline dự án",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "priority",
            "task_type",
            "start_date",
            "due_date",
            "estimated_hours",
            "actual_hours",
            "progress",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tiêu đề nhiệm vụ"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Mô tả công việc"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "task_type": forms.Select(attrs={"class": "form-select"}),
            "start_date": DateInput(attrs={"class": "form-control"}),
            "due_date": DateInput(attrs={"class": "form-control"}),
            "estimated_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "min": "0"}),
            "actual_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "min": "0"}),
            "progress": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
        }
        labels = {"priority": "Mức ưu tiên", "task_type": "Loại công việc"}

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.status = self.instance.status if self.instance.pk else initial_status(project)
        self.instance.project = project
        if not self.instance.pk:
            self.instance._pending_status = self.status
        self.fields["task_type"].queryset = project.task_types.filter(
            Q(is_active=True) | Q(pk=self.instance.task_type_id)
        )
        members = assignable_members(project)
        if self.instance.pk:
            existing = project.members.filter(user__task_assignments__task=self.instance)
            members = members | existing
            self.fields["assignees"].initial = list(existing.values_list("pk", flat=True))
        self.fields["assignees"].queryset = members.select_related("user")
        self.fields["assignees"].label_from_instance = lambda member: member.user.get_display_name()

    def clean_progress(self):
        progress = self.cleaned_data.get("progress") or 0
        if self.status.is_completed:
            return 100
        if progress >= 100:
            return 90
        return min(max(progress, 0), 100)

    def clean(self):
        cleaned = super().clean()
        due = cleaned.get("due_date")
        if due and self.project and due > self.project.end_date and not cleaned.get("confirm_outside_deadline"):
            self.add_error(
                "due_date",
                "Hạn task vượt quá deadline dự án. Đánh dấu xác nhận nếu Manager vẫn muốn tiếp tục.",
            )
        return cleaned

    def assignee_user_ids(self):
        return [member.user_id for member in self.cleaned_data.get("assignees", [])]


class QuickTaskForm(forms.Form):
    title = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Tên nhiệm vụ"}))
    priority_id = forms.ModelChoiceField(
        queryset=Priority.objects.filter(scope="TASK"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    due_date = forms.DateField(required=False, widget=DateInput(attrs={"class": "form-control"}))
    task_type = forms.ModelChoiceField(queryset=TaskType.objects.none(), required=False)

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task_type"].queryset = project.task_types.filter(is_active=True)


class CommentForm(forms.Form):
    content = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Viết bình luận..."})
    )


class ChecklistForm(forms.Form):
    title = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Thêm hạng mục"})
    )


class WorkflowForm(forms.Form):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.none(), widget=forms.CheckboxSelectMultiple, label="Các cột được sử dụng",
    )
    initial = forms.ModelChoiceField(
        queryset=Status.objects.none(), widget=forms.Select(attrs={"class": "form-select"}),
        label="Trạng thái khi tạo công việc",
    )

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        statuses = available_statuses(project)
        self.fields["statuses"].queryset = statuses
        self.fields["initial"].queryset = statuses.filter(stage=Status.Stage.TODO)


class TransitionForm(forms.Form):
    source = forms.ModelChoiceField(queryset=Status.objects.none(), label="Từ")
    target = forms.ModelChoiceField(queryset=Status.objects.none(), label="Đến")
    role = forms.ChoiceField(choices=TaskTransition.Role.choices, label="Ai được chuyển")

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        statuses = available_statuses(project)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select form-select-sm"
        self.fields["source"].queryset = statuses
        self.fields["target"].queryset = statuses


TransitionFormSet = forms.formset_factory(TransitionForm, extra=0, can_delete=True, max_num=200, validate_max=True)


class StatusForm(forms.ModelForm):
    class Meta:
        model = Status
        fields = ["name", "stage", "color", "sort_order"]
        labels = {"name": "Tên cột", "stage": "Giai đoạn", "color": "Màu", "sort_order": "Thứ tự"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "stage": forms.Select(attrs={"class": "form-select"}),
            "color": forms.TextInput(attrs={"class": "form-control form-control-color", "type": "color"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["stage"].disabled = True

    def clean_color(self):
        color = self.cleaned_data["color"]
        if not re.fullmatch(r"#[a-fA-F0-9]{6}", color):
            raise forms.ValidationError("Màu phải là mã hex 6 ký tự.")
        return color


class TaskTypeForm(forms.ModelForm):
    class Meta:
        model = TaskType
        fields = ["name"]
        labels = {"name": "Tên loại công việc"}
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}
