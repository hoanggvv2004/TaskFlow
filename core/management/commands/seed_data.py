import io
import random
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas

from accounts.models import User
from activity.services import log_activity
from core.models import Priority, Status
from notifications.models import Notification
from notifications.services import notify
from projects.models import (
    Project,
    ProjectMember,
)
from tasks.models import (
    Document,
    Task,
    TaskAssignment,
    TaskChecklist,
    TaskComment,
    TaskHistory,
    TaskWorkflow,
)


PROJECT_DEFS = [
    {
        "name": "Website E-Commerce Platform",
        "category": "Web",
        "description": "Xây dựng sàn thương mại điện tử đa nhà bán với giỏ hàng, thanh toán và quản trị đơn hàng.",
        "status": "active",
        "priority": "high",
        "offset_start": -40,
        "offset_end": 50,
        "cover": "ecommerce.jpg",
    },
    {
        "name": "Mobile Banking Application",
        "category": "Mobile",
        "description": "Ứng dụng ngân hàng số cho khách hàng cá nhân: chuyển khoản, tiết kiệm và xác thực sinh trắc học.",
        "status": "active",
        "priority": "urgent",
        "offset_start": -55,
        "offset_end": 35,
        "cover": "banking.jpg",
    },
    {
        "name": "Customer CRM System",
        "category": "Internal",
        "description": "Hệ thống quản lý khách hàng, pipeline bán hàng và chăm sóc sau bán.",
        "status": "active",
        "priority": "medium",
        "offset_start": -20,
        "offset_end": 70,
        "cover": "crm.jpg",
    },
    {
        "name": "Learning Management System",
        "category": "Education",
        "description": "Nền tảng học trực tuyến cho khóa học nội bộ, bài kiểm tra và cấp chứng chỉ.",
        "status": "planning",
        "priority": "medium",
        "offset_start": 5,
        "offset_end": 90,
        "cover": "lms.jpg",
    },
    {
        "name": "Inventory Management System",
        "category": "Operations",
        "description": "Theo dõi tồn kho nhiều kho, nhập xuất và cảnh báo thiếu hàng.",
        "status": "on-hold",
        "priority": "low",
        "offset_start": -10,
        "offset_end": 80,
        "cover": "inventory.jpg",
    },
    {
        "name": "AI Customer Support",
        "category": "AI",
        "description": "Trợ lý hỗ trợ khách hàng dùng NLP, chuyển tiếp agent và báo cáo chất lượng.",
        "status": "active",
        "priority": "high",
        "offset_start": -30,
        "offset_end": 40,
        "cover": "ai-support.jpg",
    },
    {
        "name": "Hotel Booking Platform",
        "category": "Hospitality",
        "description": "Nền tảng đặt phòng khách sạn, quản lý giá theo mùa và xác nhận đặt chỗ.",
        "status": "completed",
        "priority": "medium",
        "offset_start": -120,
        "offset_end": -10,
        "cover": "hotel.jpg",
    },
    {
        "name": "Digital Marketing Dashboard",
        "category": "Analytics",
        "description": "Bảng điều khiển chiến dịch, theo dõi ROI và hiệu suất kênh truyền thông.",
        "status": "active",
        "priority": "high",
        "offset_start": -15,
        "offset_end": 45,
        "cover": "marketing.jpg",
    },
]

TASK_TITLES = [
    "Thiết kế database",
    "Xây dựng đăng nhập",
    "Thiết kế Dashboard",
    "Phát triển API sản phẩm",
    "Tích hợp thanh toán",
    "Kiểm thử phân quyền",
    "Tối ưu responsive",
    "Viết tài liệu hệ thống",
    "Phân tích yêu cầu nghiệp vụ",
    "Thiết kế luồng người dùng",
    "Xây dựng Kanban board",
    "Tích hợp thông báo realtime",
    "Tối ưu truy vấn báo cáo",
    "Chuẩn bị dữ liệu demo",
    "Rà soát bảo mật upload",
    "Thiết kế trang hồ sơ",
    "Xây dựng lịch dự án",
    "Kiểm thử hồi quy",
    "Họp review sprint",
    "Cấu hình môi trường staging",
]


class Command(BaseCommand):
    help = "Seed demo users, projects, tasks and related data."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Xóa dữ liệu demo rồi seed lại.")

    def handle(self, *args, **options):
        random.seed(42)
        self._seed_lookups()
        if options["reset"]:
            self._reset_demo()
        if User.objects.filter(email="admin@projecthub.local").exists() and Project.objects.exists():
            self.stdout.write(self.style.WARNING("Demo data already exists. Use --reset to recreate."))
            return
        users = self._seed_users()
        projects = self._seed_projects(users)
        self._seed_tasks(users, projects)
        self._seed_documents(users, projects)
        self.stdout.write(self.style.SUCCESS("Seed data completed. See README for demo accounts."))

    def _seed_lookups(self):
        statuses = [
            ("Planning", "planning", "#6B7280", 1),
            ("Active", "active", "#5B6CFF", 2),
            ("On Hold", "on-hold", "#F59E0B", 3),
            ("Completed", "completed", "#10B981", 4),
            ("Cancelled", "cancelled", "#EF4444", 5),
        ]
        for name, slug, color, order in statuses:
            Status.objects.get_or_create(
                scope="PROJECT", slug=slug,
                defaults={"name": name, "color": color, "sort_order": order},
            )
        priorities = [
            ("Low", "low", "#86EFAC", 1),
            ("Medium", "medium", "#FDE68A", 2),
            ("High", "high", "#FDBA74", 3),
            ("Urgent", "urgent", "#FCA5A5", 4),
        ]
        for name, slug, color, order in priorities:
            Priority.objects.get_or_create(
                scope="PROJECT", slug=slug,
                defaults={"name": name, "color": color, "sort_order": order},
            )
        task_statuses = [
            ("To-do", "todo", "#9CA3AF", 1),
            ("In Progress", "in-progress", "#5B6CFF", 2),
            ("Review", "review", "#F59E0B", 3),
            ("Completed", "completed", "#10B981", 4),
            ("Blocked", "blocked", "#EF4444", 5),
        ]
        for name, slug, color, order in task_statuses:
            Status.objects.get_or_create(
                scope="TASK",
                slug=slug,
                defaults={"name": name, "color": color, "sort_order": order,
                          "stage": "delayed" if slug == "blocked" else slug},
            )
        for name, slug, color, order in priorities:
            Priority.objects.get_or_create(
                scope="TASK", slug=slug,
                defaults={"name": name, "color": color, "sort_order": order},
            )

    def _reset_demo(self):
        from django.db.models import QuerySet

        from activity.models import ActivityLog
        from core.models import Priority, Status
        from projects.models import ProjectPriority, ProjectStatus
        from tasks.models import TaskPriority, TaskStatus

        Document.objects.all().delete()
        TaskComment.objects.all().delete()
        TaskChecklist.objects.all().delete()
        TaskHistory.objects.all().delete()
        TaskAssignment.objects.all().delete()
        QuerySet.delete(Task.all_objects.all())
        TaskWorkflow.objects.all().delete()
        ProjectMember.objects.all().delete()
        QuerySet.delete(Project.all_objects.all())
        Status.objects.filter(scope="PROJECT").delete()
        Status.objects.filter(scope="TASK").delete()
        Priority.objects.filter(scope="PROJECT").delete()
        Priority.objects.filter(scope="TASK").delete()
        Notification.objects.all().delete()
        ActivityLog.objects.all().delete()
        QuerySet.delete(User.all_objects.exclude(is_superuser=True))

    def _make_avatar(self, initials, color):
        image = Image.new("RGB", (256, 256), color)
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("arial.ttf", 92)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), initials, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((256 - w) / 2, (256 - h) / 2 - 8), initials, fill="white", font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return ContentFile(buffer.getvalue(), name=f"{initials.lower()}.png")

    def _make_cover(self, title, color):
        image = Image.new("RGB", (1400, 640), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 480, 1400, 640), fill=(17, 24, 39))
        try:
            font = ImageFont.truetype("arial.ttf", 42)
        except OSError:
            font = ImageFont.load_default()
        draw.text((48, 520), title, fill="white", font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88)
        return ContentFile(buffer.getvalue(), name="cover.jpg")

    def _cover_from_file(self, filename, title, color):
        path = Path(settings.BASE_DIR) / "static" / "images" / "covers" / filename
        if path.exists():
            return ContentFile(path.read_bytes(), name=filename)
        return self._make_cover(title, color)

    def _seed_users(self):
        palette = ["#5B6CFF", "#6366F1", "#7C3AED", "#0EA5E9", "#059669", "#D97706", "#DC2626", "#334155"]
        people = [
            ("admin", "admin@projecthub.local", "Admin@123", "Minh", "Quản trị", User.Role.ADMIN, "System Admin"),
            ("lan.pham", "manager@projecthub.local", "Manager@123", "Phạm Thu Lan", "", User.Role.PROJECT_MANAGER, "Delivery Manager"),
            ("hoang.nguyen", "hoang.nguyen@projecthub.local", "Manager@123", "Nguyễn Việt Hoàng", "", User.Role.PROJECT_MANAGER, "Project Manager"),
            ("mai.tran", "mai.tran@projecthub.local", "Manager@123", "Trần Khánh Mai", "", User.Role.PROJECT_MANAGER, "Product Manager"),
            ("member", "member@projecthub.local", "Member@123", "Lê Quốc Bảo", "", User.Role.MEMBER, "Frontend Developer"),
            ("an.nguyen", "an.nguyen@projecthub.local", "Member@123", "Nguyễn Văn An", "", User.Role.MEMBER, "Backend Developer"),
            ("duc.tran", "duc.tran@projecthub.local", "Member@123", "Trần Minh Đức", "", User.Role.MEMBER, "QA Engineer"),
            ("chi.le", "chi.le@projecthub.local", "Member@123", "Lê Bảo Chi", "", User.Role.MEMBER, "UI Designer"),
            ("hung.pham", "hung.pham@projecthub.local", "Member@123", "Phạm Quốc Hưng", "", User.Role.MEMBER, "DevOps"),
            ("thao.vo", "thao.vo@projecthub.local", "Member@123", "Võ Thanh Thảo", "", User.Role.MEMBER, "Business Analyst"),
            ("khoa.bui", "khoa.bui@projecthub.local", "Member@123", "Bùi Đăng Khoa", "", User.Role.MEMBER, "Mobile Developer"),
            ("ha.dinh", "ha.dinh@projecthub.local", "Member@123", "Đinh Thu Hà", "", User.Role.MEMBER, "Content Lead"),
            ("nam.do", "nam.do@projecthub.local", "Member@123", "Đỗ Hoàng Nam", "", User.Role.MEMBER, "Data Analyst"),
            ("yen.ly", "yen.ly@projecthub.local", "Member@123", "Lý Hải Yến", "", User.Role.MEMBER, "QA Engineer"),
            ("tuan.vu", "tuan.vu@projecthub.local", "Member@123", "Vũ Anh Tuấn", "", User.Role.MEMBER, "Fullstack Developer"),
            ("my.ngo", "my.ngo@projecthub.local", "Member@123", "Ngô Trà My", "", User.Role.MEMBER, "UX Researcher"),
            ("phuc.lam", "phuc.lam@projecthub.local", "Member@123", "Lâm Gia Phúc", "", User.Role.MEMBER, "Backend Developer"),
            ("quynh.ho", "quynh.ho@projecthub.local", "Member@123", "Hồ Nhật Quỳnh", "", User.Role.MEMBER, "Marketing"),
        ]
        users = []
        for index, (username, email, password, first, last, role, title) in enumerate(people):
            user, created = User.all_objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "role": role,
                    "job_title": title,
                    "phone": f"090{1000000 + index}",
                    "is_staff": role == User.Role.ADMIN,
                    "is_superuser": role == User.Role.ADMIN,
                    "bio": f"{first} phụ trách {title.lower()} tại TaskFlow.",
                    "address": "Quận 1, TP. Hồ Chí Minh",
                },
            )
            if created:
                user.set_password(password)
                user.avatar.save(f"{username}.png", self._make_avatar(user.get_initials(), palette[index % len(palette)]), save=False)
                user.save()
            users.append(user)
        return users

    def _seed_projects(self, users):
        admin = users[0]
        managers = [u for u in users if u.role == User.Role.PROJECT_MANAGER]
        members = [u for u in users if u.role == User.Role.MEMBER]
        statuses = {s.slug: s for s in Status.objects.filter(scope="PROJECT")}
        priorities = {p.slug: p for p in Priority.objects.filter(scope="PROJECT")}
        covers = ["#5B6CFF", "#0F766E", "#7C3AED", "#0369A1", "#B45309", "#BE123C", "#334155", "#2563EB"]
        today = timezone.localdate()
        projects = []
        for index, item in enumerate(PROJECT_DEFS):
            owner = managers[index % len(managers)]
            project = Project.objects.create(
                name=item["name"],
                description=item["description"],
                category=item["category"],
                start_date=today + timedelta(days=item["offset_start"]),
                end_date=today + timedelta(days=item["offset_end"]),
                status=statuses[item["status"]],
                priority=priorities[item["priority"]],
                owner=owner,
            )
            cover_file = self._cover_from_file(item.get("cover") or "ecommerce.jpg", item["name"], covers[index])
            project.cover_image.save(cover_file.name, cover_file, save=True)
            ProjectMember.objects.create(project=project, user=owner, role=ProjectMember.Role.OWNER, added_by=admin)
            if admin not in {owner}:
                ProjectMember.objects.get_or_create(
                    project=project,
                    user=admin,
                    defaults={"role": ProjectMember.Role.MANAGER, "added_by": owner},
                )
            selected = members[index : index + 6]
            if len(selected) < 6:
                selected = members[: 6 - len(selected)] + selected
            for member in selected:
                role = ProjectMember.Role.MANAGER if member == selected[0] else ProjectMember.Role.MEMBER
                ProjectMember.objects.get_or_create(
                    project=project,
                    user=member,
                    defaults={"role": role, "added_by": owner},
                )
            log_activity(owner, "project_created", f"{owner.get_display_name()} tạo dự án {project.name}.", project=project)
            projects.append(project)
        return projects

    def _seed_tasks(self, users, projects):
        statuses = list(Status.objects.filter(scope="TASK", slug__in=["todo", "in-progress", "review", "completed"]))
        blocked = Status.objects.filter(scope="TASK", slug="blocked").first()
        priorities = list(Priority.objects.filter(scope="TASK"))
        today = timezone.localdate()
        count = 0
        comments = [
            "Mình đã xong phần phân tích, mọi người review giúp nhé.",
            "Cần bổ sung constraint unique trước khi merge.",
            "Deadline hơi gấp, đề xuất dời sang cuối tuần.",
            "Đã đẩy bản nháp lên môi trường staging.",
            "Checklist còn thiếu bước kiểm thử phân quyền.",
        ]
        for project in projects:
            members = list(project.members.select_related("user"))
            people = [m.user for m in members]
            owner = project.owner
            task_count = 8 if project.status.slug == "planning" else 10
            for index in range(task_count):
                status = statuses[index % len(statuses)]
                if project.status.slug == "completed":
                    status = Status.objects.get(scope="TASK", slug="completed")
                if index == 7 and blocked:
                    status = blocked
                priority = priorities[index % len(priorities)]
                start = project.start_date + timedelta(days=index * 2)
                due = start + timedelta(days=8 + (index % 5))
                if index % 6 == 0:
                    due = today - timedelta(days=2)
                if index % 6 == 1:
                    due = today + timedelta(days=2)
                progress = 100 if status.slug == "completed" else (10 + index * 8) % 90
                task = Task.objects.create(
                    title=TASK_TITLES[index % len(TASK_TITLES)] + f" · {project.category}",
                    description=f"{TASK_TITLES[index % len(TASK_TITLES)]} cho dự án {project.name}.",
                    project=project,
                    status=status,
                    priority=priority,
                    start_date=start,
                    due_date=due,
                    estimated_hours=8 + index,
                    actual_hours=4 if status.slug == "completed" else 1,
                    progress=progress,
                    created_by=owner,
                )
                assignees = random.sample(people, k=min(len(people), 2 + index % 2))
                for user in assignees:
                    TaskAssignment.objects.get_or_create(task=task, user=user, defaults={"assigned_by": owner})
                    notify(
                        user,
                        Notification.Type.TASK_ASSIGNED,
                        "Bạn được giao nhiệm vụ",
                        f"{owner.get_display_name()} đã giao {task.code} cho bạn.",
                        task.get_absolute_url(),
                    )
                TaskHistory.objects.create(task=task, user=owner, new_status=status, note="Khởi tạo")
                if status.slug != "todo":
                    previous = Status.objects.get(scope="TASK", slug="todo")
                    TaskHistory.objects.create(task=task, user=assignees[0], old_status=previous, new_status=status)
                    log_activity(
                        assignees[0],
                        "task_status_changed",
                        f"{assignees[0].get_display_name()} thay đổi {task.code} từ To-do sang {status.name}.",
                        project=project,
                        task=task,
                    )
                TaskChecklist.objects.bulk_create(
                    [
                        TaskChecklist(task=task, title="Phân tích yêu cầu", is_completed=True, created_by=owner),
                        TaskChecklist(task=task, title="Thiết kế database", is_completed=status.slug != "todo", created_by=owner),
                        TaskChecklist(task=task, title="Xây dựng API", is_completed=status.slug == "completed", created_by=owner),
                        TaskChecklist(task=task, title="Testing", is_completed=status.slug == "completed", created_by=owner),
                    ]
                )
                if index % 2 == 0:
                    author = assignees[0]
                    TaskComment.objects.create(task=task, user=author, content=comments[index % len(comments)])
                    notify(
                        owner,
                        Notification.Type.TASK_COMMENT,
                        "Bình luận mới",
                        f"{author.get_display_name()} vừa bình luận trong {task.code}.",
                        task.get_absolute_url(),
                    )
                log_activity(owner, "task_created", f"{owner.get_display_name()} tạo {task.code}.", project=project, task=task)
                if task.is_overdue:
                    for user in assignees:
                        notify(
                            user,
                            Notification.Type.TASK_OVERDUE,
                            "Nhiệm vụ trễ hạn",
                            f"{task.code} đã quá hạn.",
                            task.get_absolute_url(),
                        )
                elif task.is_due_soon:
                    for user in assignees:
                        notify(
                            user,
                            Notification.Type.TASK_DUE_SOON,
                            "Nhiệm vụ sắp đến hạn",
                            f"{task.code} sẽ đến hạn trong 3 ngày.",
                            task.get_absolute_url(),
                        )
                count += 1
        self.stdout.write(f"Created {count} tasks.")

    def _seed_documents(self, users, projects):
        media = Path(settings.MEDIA_ROOT) / "documents"
        media.mkdir(parents=True, exist_ok=True)
        for project in projects[:6]:
            uploader = project.owner
            task = project.tasks.first()
            pdf_buffer = io.BytesIO()
            pdf = canvas.Canvas(pdf_buffer)
            pdf.drawString(72, 800, f"Tai lieu du an {project.code}")
            pdf.save()
            pdf_bytes = pdf_buffer.getvalue()
            doc = Document(
                name=f"Ke hoach {project.code}",
                original_name=f"{project.code}-plan.pdf",
                file_type="pdf",
                file_size=len(pdf_bytes),
                project=project,
                task=task,
                uploaded_by=uploader,
            )
            doc.file.save(f"{project.code.lower()}-plan.pdf", ContentFile(pdf_bytes), save=True)
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as archive:
                archive.writestr("readme.txt", f"Tai lieu {project.code}")
            zip_bytes = zip_buffer.getvalue()
            bundle = Document(
                name=f"Bundle {project.code}",
                original_name=f"{project.code}-bundle.zip",
                file_type="zip",
                file_size=len(zip_bytes),
                project=project,
                uploaded_by=uploader,
            )
            bundle.file.save(f"{project.code.lower()}-bundle.zip", ContentFile(zip_bytes), save=True)
            log_activity(uploader, "document_uploaded", f"{uploader.get_display_name()} upload report.pdf.", project=project, task=task)
