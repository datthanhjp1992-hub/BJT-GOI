"""Tính lại `is_mastered` theo khoảng cách ôn (10/10/2026).

Trước: srs_level >= 5 (5 lần ôn thành công liên tiếp).
Sau:   card_state = "review" và interval_days >= 21 — xem apps/learning/srs.py
       (MASTERED_INTERVAL, is_mastered). Chạy lại bao nhiêu lần cũng ra cùng kết quả.
Quay ngược (migrate learning 0002) thì trả về luật cũ.
"""
from django.db import migrations

MASTERED_INTERVAL = 21  # = srs.MASTERED_INTERVAL lúc viết migration (không import để migration đứng yên)


def by_interval(apps, schema_editor):
    Progress = apps.get_model("learning", "UserVocabularyProgress")
    mastered = {"card_state": "review", "interval_days__gte": MASTERED_INTERVAL}
    Progress.objects.filter(**mastered).update(is_mastered=True)
    Progress.objects.exclude(**mastered).update(is_mastered=False)


def by_repetitions(apps, schema_editor):
    Progress = apps.get_model("learning", "UserVocabularyProgress")
    Progress.objects.filter(srs_level__gte=5).update(is_mastered=True)
    Progress.objects.filter(srs_level__lt=5).update(is_mastered=False)


class Migration(migrations.Migration):
    dependencies = [("learning", "0002_learning_steps")]
    operations = [migrations.RunPython(by_interval, by_repetitions)]
