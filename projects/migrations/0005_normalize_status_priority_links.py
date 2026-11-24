import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_status_project_related_name"),
        ("projects", "0004_projectpriority_priority_projectstatus_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="project",
            name="projects_pr_status__117b0d_idx",
        ),
        migrations.RenameModel(
            old_name="ProjectStatus",
            new_name="LegacyProjectStatus",
        ),
        migrations.RenameModel(
            old_name="ProjectPriority",
            new_name="LegacyProjectPriority",
        ),
        migrations.RunSQL(
            sql=[
                "ALTER TABLE projects_legacyprojectstatus DROP FOREIGN KEY projects_projectstatus_status_id_53113850_fk_core_status_id",
                "ALTER TABLE projects_legacyprojectstatus ADD CONSTRAINT legacy_projectstatus_status_fk FOREIGN KEY (status_id) REFERENCES core_status(id)",
                "ALTER TABLE projects_legacyprojectpriority DROP FOREIGN KEY projects_projectprio_priority_id_90b0d435_fk_core_prio",
                "ALTER TABLE projects_legacyprojectpriority ADD CONSTRAINT legacy_projectpriority_priority_fk FOREIGN KEY (priority_id) REFERENCES core_priority(id)",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RenameField(
            model_name="project",
            old_name="status",
            new_name="legacy_status",
        ),
        migrations.RenameField(
            model_name="project",
            old_name="priority",
            new_name="legacy_priority",
        ),
        migrations.AlterField(
            model_name="project",
            name="legacy_status",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="projects.legacyprojectstatus",
            ),
        ),
        migrations.AlterField(
            model_name="project",
            name="legacy_priority",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="projects.legacyprojectpriority",
            ),
        ),
        migrations.CreateModel(
            name="ProjectStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_current", models.BooleanField(default=None, null=True)),
                ("changed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_links", to="projects.project")),
                ("status", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="project_links", to="core.status")),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("project", "is_current"), name="uniq_project_status_current"),
                ],
                "indexes": [
                    models.Index(fields=["project", "changed_at"], name="idx_project_status_changed"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProjectPriority",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_current", models.BooleanField(default=None, null=True)),
                ("changed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="priority_links", to="projects.project")),
                ("priority", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="project_links", to="core.priority")),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("project", "is_current"), name="uniq_project_priority_current"),
                ],
                "indexes": [
                    models.Index(fields=["project", "changed_at"], name="idx_project_priority_changed"),
                ],
            },
        ),
    ]
