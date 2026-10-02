"""Gỡ keep-alive dạng luồng nền (02/10/2026).

Luồng nền tự ping /healthz/ làm server Render free tắc nghẽn nên đã tắt từ
25/09/2026, nay gỡ hẳn: xoá bảng SiteSetting (chỉ chứa cấu hình keep-alive) và
các dòng MasterCode code_type "17" (chu kỳ ping). Giữ server thức sẽ làm bằng
cron ngoài gọi /healthz/ — xem spec.md mục T4.1.

Không đảo ngược có ý nghĩa: seed_mastercode không còn code_type "17".
"""
from django.db import migrations

KEEPALIVE_INTERVAL_CODE_TYPE = "17"


def drop_keepalive_codes(apps, schema_editor):
    MasterCode = apps.get_model("core", "MasterCode")
    MasterCode.objects.filter(code_type=KEEPALIVE_INTERVAL_CODE_TYPE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_sitesetting"),
    ]

    operations = [
        migrations.RunPython(drop_keepalive_codes, migrations.RunPython.noop),
        migrations.DeleteModel(name="SiteSetting"),
    ]
