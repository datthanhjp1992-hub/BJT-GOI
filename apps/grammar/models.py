"""
Mẫu ngữ pháp N3–N1 (文型) — 500 mẫu lấy từ bảng grammar_pattern của bjt.db (BJT-WEB),
khung chương theo 日本語表現文型500; câu ví dụ/giải thích là tự soạn, không chép sách.

Bảng phẳng, một dòng một mẫu: không đưa vào `Vocabulary` vì sẽ kéo vào hàng đợi SRS.
Nguồn nhập: docs/data/grammar/grammar_pattern.csv qua scripts/import_grammar.py.
"""
from django.db import models

from apps.core.models import AuditableModel
from apps.core.properties import label

# Thứ tự chương theo mục lục 日本語表現文型500 (ghi trong source_file của bjt.db).
# shortcut: 5 chương cuối (話題…判断・推量) chưa xác nhận được số chương, xếp tạm.
# Tên tiếng Việt ở label.properties: grammar.chapter.<tên chương>.
CHAPTERS = [
    "対象", "目的手段", "起点終点", "時点", "時間的前後", "相関", "付帯・非付帯", "限定",
    "非限定・付加", "比較・対比", "判断の視点", "基準", "関連・対応", "無関係・例外", "例示",
    "強調", "仮定条件", "逆接仮定条件", "難易", "傾向", "経過・結末", "否定", "伝聞・推量",
    "心情強調", "勧め禁止", "主張・断定", "話題", "原因・理由", "逆接", "程度", "判断・推量",
]


def chapter_name_vi(category):
    return label(f"grammar.chapter.{category}", default="")


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
