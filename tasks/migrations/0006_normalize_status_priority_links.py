import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_status_project_related_name"),
        ("projects", "0005_normalize_status_priority_links"),
        ("tasks", "0005_link_shared_status_priority"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="task",
            name="tasks_task_project_d48c46_idx",
        ),
        migrations.AlterField(
            model_name="taskstatus",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="projects.project",
            ),
        ),
        migrations.RenameModel(
            old_name="TaskStatus",
            new_name="LegacyTaskStatus",
        ),
        migrations.RenameModel(
            old_name="TaskPriority",
            new_name="LegacyTaskPriority",
        ),
        migrations.RunSQL(
            sql=[
                "ALTER TABLE tasks_legacytaskstatus DROP FOREIGN KEY tasks_taskstatus_status_id_712adfe2_fk_core_status_id",
                "ALTER TABLE tasks_legacytaskstatus ADD CONSTRAINT legacy_taskstatus_status_fk FOREIGN KEY (status_id) REFERENCES core_status(id)",
                "ALTER TABLE tasks_legacytaskpriority DROP FOREIGN KEY tasks_taskpriority_priority_id_fd251b25_fk_core_priority_id",
                "ALTER TABLE tasks_legacytaskpriority ADD CONSTRAINT legacy_taskpriority_priority_fk FOREIGN KEY (priority_id) REFERENCES core_priority(id)",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RenameField(
            model_name="task",
            old_name="status",
            new_name="legacy_status",
        ),
        migrations.RenameField(
            model_name="task",
            old_name="priority",
            new_name="legacy_priority",
        ),
        migrations.AlterField(
            model_name="task",
            name="legacy_status",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tasks.legacytaskstatus",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="legacy_priority",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tasks.legacytaskpriority",
            ),
        ),
        migrations.CreateModel(
            name="TaskStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_current", models.BooleanField(default=None, null=True)),
                ("changed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_links", to="tasks.task")),
                ("status", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="task_links", to="core.status")),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("task", "is_current"), name="uniq_task_status_current"),
                ],
                "indexes": [
                    models.Index(fields=["task", "changed_at"], name="idx_task_status_changed"),
                ],
            },
        ),
        migrations.CreateModel(
            name="TaskPriority",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_current", models.BooleanField(default=None, null=True)),
                ("changed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="priority_links", to="tasks.task")),
                ("priority", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="task_links", to="core.priority")),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("task", "is_current"), name="uniq_task_priority_current"),
                ],
                "indexes": [
                    models.Index(fields=["task", "changed_at"], name="idx_task_priority_changed"),
                ],
            },
        ),
    ]
