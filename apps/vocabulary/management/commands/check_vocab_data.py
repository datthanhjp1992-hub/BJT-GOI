"""Hậu kiểm dữ liệu từ đồng nghĩa. KHÔNG ghi gì vào DB.

    python manage.py check_vocab_data --settings=config.settings.supabase

Spec: docs/SPEC_TU_DONG_NGHIA.md T3. Lỗi (thoát mã 1): cặp lệch một chiều, chip
synonyms_note trùng từ đã liên kết hoặc trùng chính từ đó. Chỉ báo, không tính lỗi:
liên kết tới từ đã xoá mềm (thẻ tự ẩn, khôi phục từ là hiện lại).
"""
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q

from apps.vocabulary.models import Vocabulary, VocabularySynonym


class Command(BaseCommand):
    help = "Hậu kiểm dữ liệu từ đồng nghĩa (chỉ đọc)."

    def handle(self, *args, **options):
        self.failures = []
        self._one_sided()
        self._notes()
        self._soft_deleted()

        self.stdout.write("")
        if self.failures:
            self.stdout.write(self.style.ERROR(f"CÓ {len(self.failures)} VẤN ĐỀ:"))
            for f in self.failures:
                self.stdout.write(self.style.ERROR(f"  - {f}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Tất cả phép kiểm đều đạt."))

    def _row(self, label, bad, fail=True):
        mark = self.style.SUCCESS("OK") if not bad else (self.style.ERROR("LỖI") if fail else self.style.WARNING("BÁO"))
        self.stdout.write(f"  {label:<44} {len(bad):>5} {mark}")
        if fail:
            self.failures.extend(bad)
        else:
            for b in bad:
                self.stdout.write(f"      · {b}")

    def _one_sided(self):
        """Mỗi dòng A→B phải có B→A — thiếu khi ai đó sửa `synonym` của dòng có sẵn trong admin."""
        self.stdout.write(self.style.MIGRATE_HEADING("\n[1] Cặp đồng nghĩa hai chiều"))
        reverse = VocabularySynonym.objects.filter(vocabulary=OuterRef("synonym"), synonym=OuterRef("vocabulary"))
        rows = VocabularySynonym.objects.filter(~Exists(reverse)).select_related("vocabulary", "synonym")
        self.stdout.write(f"  {'tổng số dòng':<44} {VocabularySynonym.objects.count():>5}")
        self._row("dòng thiếu chiều ngược", [f"{r.vocabulary.word} → {r.synonym.word} (thiếu chiều ngược)" for r in rows])

    def _notes(self):
        """synonyms_note không được lặp từ đã liên kết hay chính từ đó — thẻ sẽ hiện hai chip giống nhau."""
        self.stdout.write(self.style.MIGRATE_HEADING("\n[2] Ô synonyms_note"))
        bad = []
        for word in Vocabulary.objects.exclude(synonyms_note="").prefetch_related("synonyms"):
            chips = word.synonym_chips()
            linked = {text for text, is_linked in chips if is_linked}
            for text, is_linked in chips:
                if not is_linked and (text in linked or text == word.word):
                    bad.append(f"{word.word}: synonyms_note có 「{text}」 trùng từ đã liên kết / chính từ đó")
        self._row("chip synonyms_note bị trùng", bad)

    def _soft_deleted(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[3] Liên kết tới từ đã xoá mềm"))
        rows = VocabularySynonym.objects.filter(
            Q(vocabulary__is_deleted=True) | Q(synonym__is_deleted=True)
        ).select_related("vocabulary", "synonym")
        self._row("liên kết có từ đã xoá (đang ẩn trên thẻ)",
                  [f"{r.vocabulary.word} → {r.synonym.word}" for r in rows], fail=False)
