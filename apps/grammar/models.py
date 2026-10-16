"""
Mẫu ngữ pháp N3–N1 (文型) — 500 mẫu lấy từ bảng grammar_pattern của bjt.db (BJT-WEB),
khung chương theo 日本語表現文型500; câu ví dụ/giải thích là tự soạn, không chép sách.

Bảng phẳng, một dòng một mẫu: không đưa vào `Vocabulary` vì sẽ kéo vào hàng đợi SRS.
Nguồn nhập: docs/data/grammar/grammar_pattern.csv qua scripts/import_grammar.py.
"""
from django.db import models

from apps.core.models import AuditableModel


class GrammarPattern(AuditableModel):
    pattern = models.CharField(max_length=60, unique=True, help_text="vd 〜につけ(て) — khoá nhập lại")
    meaning_vi = models.CharField(max_length=200)
    connection_form = models.CharField(max_length=150, blank=True)
    example_jp = models.TextField(blank=True)
    example_vi = models.TextField(blank=True)
    level = models.CharField(max_length=10, blank=True, db_index=True, help_text="N1 / N2 / N3/N2")
    category = models.CharField(max_length=30, blank=True, db_index=True, help_text="Chương, vd 逆接")
    note = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "pattern"]
        verbose_name = "Mẫu ngữ pháp"
        verbose_name_plural = "Mẫu ngữ pháp"

    def __str__(self):
        return self.pattern
