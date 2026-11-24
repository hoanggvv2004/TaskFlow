from django import forms
from django.db.models import Q

from accounts.models import Department, User
from core.models import Priority, Status
from core.permissions import is_admin
from projects.models import Project, ProjectMember
from projects.services import eligible_project_users


class DateInput(forms.DateInput):
    input_type = "date"


class ProjectForm(forms.ModelForm):
    status = forms.ModelChoiceField(queryset=Status.objects.filter(scope="PROJECT"), required=True)
    priority = forms.ModelChoiceField(queryset=Priority.objects.filter(scope="PROJECT"), required=True)

    class Meta:
        model = Project
        fields = [
            "name",
            "description",
            "category",
            "department",
            "start_date",
            "end_date",
            "status",
            "priority",
            "cover_image",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tên dự án", "required": True}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Mô tả ngắn về mục tiêu dự án"}
            ),
            "category": forms.TextInput(attrs={"class": "form-control", "placeholder": "Web, Mobile, Internal..."}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "start_date": DateInput(attrs={"class": "form-control"}),
            "end_date": DateInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "cover_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        field = self.fields["department"]
        field.empty_label = "Chưa phân phòng"
        field.queryset = Department.objects.filter(Q(is_active=True) | Q(pk=self.instance.department_id))
        if not is_admin(actor):
            if self.instance.pk:
                field.disabled = True
            elif actor and actor.department_id:
                field.queryset = field.queryset.filter(pk=actor.department_id, manager=actor)
                field.required = True
                self.initial["department"] = actor.department_id
            else:
                field.queryset = Department.objects.none()
                field.disabled = True

    def clean_department(self):
        department = self.cleaned_data["department"]
        if not self.instance.pk or not department or department.pk == self.instance.department_id:
            return department
        from tasks.models import Task, TaskAssignment

        tasks = Task.objects.open_tasks().filter(project=self.instance)
        assigned_ids = TaskAssignment.objects.filter(task__in=tasks).values("user_id")
        department_ids = list(User.all_objects.select_for_update().filter(pk__in=assigned_ids)
                              .order_by("pk").values_list("department_id", flat=True))
        if any(current != department.pk for current in department_ids):
            raise forms.ValidationError("Hãy bàn giao công việc đang mở cho người thuộc phòng mới trước khi đổi phòng.")
        return department

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "Ngày kết thúc không được trước ngày bắt đầu.")
        return cleaned


class ProjectMemberForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Thành viên",
    )
    role = forms.ChoiceField(
        choices=[c for c in ProjectMember.Role.choices if c[0] != ProjectMember.Role.OWNER],
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Vai trò",
    )

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = eligible_project_users(project).exclude(project_memberships__project=project)
        self.fields["user"].label_from_instance = lambda user: f"{user.get_display_name()} (@{user.username})"


class ProjectFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Tìm dự án"}))
    status = forms.ModelChoiceField(
        queryset=Status.objects.filter(scope="PROJECT"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    priority = forms.ModelChoiceField(
        queryset=Priority.objects.filter(scope="PROJECT"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    manager = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=[User.Role.ADMIN, User.Role.PROJECT_MANAGER]),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("-created_at", "Mới nhất"),
            ("name", "Tên A-Z"),
            ("-name", "Tên Z-A"),
            ("end_date", "Deadline gần nhất"),
            ("-end_date", "Deadline xa nhất"),
            ("current_priority_order", "Ưu tiên"),
            ("current_status_order", "Trạng thái"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
