"""Dọn dữ liệu MasterCode của cấp độ BJT (code_type "05").

Từ 13/09/2026 từ vựng phân loại theo CHỦ ĐỀ, không còn cấp độ BJT. Ba field
dùng code_type này đã bị xoá ở accounts/0002, vocabulary/0003, gamification/0002.
Nếu không dọn, 6 row J5..J1+ vẫn nằm lại trong `core_mastercode` và sẽ hiện ra
ở màn nhập/xuất dữ liệu như thể còn dùng.

Không đảo ngược được (irreversible) một cách có ý nghĩa: chạy lại
`seed_mastercode` cũng không tạo lại vì code_type 05 đã bị gỡ khỏi SEED_DATA.
"""
from django.db import migrations

BJT_LEVEL_CODE_TYPE = "05"


def drop_bjt_levels(apps, schema_editor):
    MasterCode = apps.get_model("core", "MasterCode")
    MasterCode.objects.filter(code_type=BJT_LEVEL_CODE_TYPE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(drop_bjt_levels, migrations.RunPython.noop),
    ]
