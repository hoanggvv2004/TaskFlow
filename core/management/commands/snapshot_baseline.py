import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = "Snapshot or compare the normalized database baseline."

    def add_arguments(self, parser):
        parser.add_argument("--compare", type=str, help="Compare against a baseline JSON file.")

    def handle(self, *args, **options):
        migrations = list(
            MigrationRecorder(connection).applied_migrations()
        )
        migration_names = sorted(
            f"{app}.{name}" for app, name in migrations
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' "
                "ORDER BY TABLE_NAME"
            )
            tables = [row[0] for row in cursor.fetchall()]

        snapshot = {
            "migrations": migration_names,
            "tables": tables,
        }

        compare = options.get("compare")
        if compare:
            path = Path(compare)
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.exists():
                raise CommandError(f"Baseline file not found: {path}")
            baseline = json.loads(path.read_text(encoding="utf-8"))
            differences = {
                key: {
                    "baseline": baseline.get(key),
                    "current": snapshot.get(key),
                }
                for key in ("migrations", "tables")
                if baseline.get(key) != snapshot.get(key)
            }
            if differences:
                raise CommandError(
                    "Baseline differences: "
                    + json.dumps(differences, ensure_ascii=False)
                )
            self.stdout.write("0 differences")
            return

        path = Path("baseline.json")
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.stdout.write("Snapshot written to baseline.json")
