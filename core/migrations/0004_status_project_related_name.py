import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_backfill_status_stage_project"),
        ("projects", "0004_projectpriority_priority_projectstatus_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="status",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="custom_task_statuses",
                to="projects.project",
            ),
        ),
    ]
