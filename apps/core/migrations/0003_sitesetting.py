from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_singleton(apps, schema_editor):
    SiteSetting = apps.get_model("core", "SiteSetting")
    SiteSetting.objects.get_or_create(pk=1)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_drop_bjt_level_mastercode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("keepalive_enabled", models.BooleanField(default=True, help_text="Bật = cứ mỗi chu kỳ tự gọi /healthz/ để Render free không cho server ngủ.")),
                ("keepalive_interval_code", models.CharField(default="5", help_text="MasterCode code_type 17 — code chính là số phút giữa hai lần ping.", max_length=10)),
                ("keepalive_last_ping_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("keepalive_last_status", models.CharField(blank=True, editable=False, max_length=255)),
                ("keepalive_last_ok", models.BooleanField(blank=True, editable=False, null=True)),
                ("created_by", models.ForeignKey(blank=True, editable=False, help_text="User who created this record (null = created by system).", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, editable=False, help_text="User who last updated this record.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Cài đặt hệ thống",
                "verbose_name_plural": "Cài đặt hệ thống",
            },
        ),
        migrations.RunPython(create_singleton, migrations.RunPython.noop),
    ]
