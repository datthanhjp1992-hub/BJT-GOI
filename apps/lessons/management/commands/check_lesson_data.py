"""Hậu kiểm dữ liệu Học theo bài (Quyển 1) sau khi nạp. KHÔNG ghi gì vào DB.

    python manage.py check_lesson_data --settings=config.settings.supabase

Số liệu kỳ vọng = số dòng của docs/data/lessons/*.csv (xuất từ bjt.db ngày 17/10/2026).
Sửa CSV thì sửa luôn EXPECTED, đừng nới lỏng phép kiểm. Spec: docs/SPEC_LUYEN_TAP_BAI.md T2.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.lessons.models import (
    BLANK_RE,
    Drill,
    DrillItem,
    Lesson,
    PolitenessPhrase,
    Roleplay,
    RoleplayBlank,
    RoleplayLine,
    Unit,
)

EXPECTED = {
    "unit": 12,
    "lesson": 45,
    "drill": 34,
    "drill_item": 102,
    "roleplay": 24,
    "roleplay_line": 117,
    "roleplay_blank": 65,
    "politeness_phrase": 82,
}
DRILL_ITEMS = 3          # mỗi bài luyện thay thế đúng 3 câu
ROLEPLAYS_PER_UNIT = 2   # mỗi chương 2 đoạn đóng vai
PHRASES_PER_LESSON = 2   # bài nào có câu lịch sự thì có đúng 2 câu, khác mức


class Command(BaseCommand):
    help = "Hậu kiểm dữ liệu Học theo bài (chỉ đọc)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-expected", action="store_true",
            help="Bỏ qua phần đối chiếu số dòng kỳ vọng, chỉ soát tính nhất quán.",
        )

    def handle(self, *args, **options):
        self.failures = []
        self._counts(skip_expected=options["no_expected"])
        self._groups()
        self._blanks()
        self._politeness()
        self._empty()

        self.stdout.write("")
        if self.failures:
            self.stdout.write(self.style.ERROR(f"CÓ {len(self.failures)} VẤN ĐỀ:"))
            for f in self.failures:
                self.stdout.write(self.style.ERROR(f"  - {f}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Tất cả phép kiểm đều đạt."))

    def _fail(self, msg):
        self.failures.append(msg)

    def _row(self, label, got, want):
        ok = got == want
        mark = self.style.SUCCESS("OK") if ok else self.style.ERROR("LỆCH")
        self.stdout.write(f"  {label:<34} {got:>5} / kỳ vọng {want:<5} {mark}")
        if not ok:
            self._fail(f"{label}: có {got}, kỳ vọng {want}")

    def _counts(self, skip_expected):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[1] Số dòng từng bảng"))
        got = {
            "unit": Unit.objects.count(),
            "lesson": Lesson.objects.count(),
            "drill": Drill.objects.count(),
            "drill_item": DrillItem.objects.count(),
            "roleplay": Roleplay.objects.count(),
            "roleplay_line": RoleplayLine.objects.count(),
            "roleplay_blank": RoleplayBlank.objects.count(),
            "politeness_phrase": PolitenessPhrase.objects.count(),
        }
        for k, v in got.items():
            if skip_expected:
                self.stdout.write(f"  {k:<34} {v:>5}")
            else:
                self._row(k, v, EXPECTED[k])

    def _groups(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[2] Số câu mỗi nhóm"))
        bad = [f"bài {d.lesson.scene_no}: {d.n} câu" for d in
               Drill.objects.select_related("lesson").annotate(n=Count("items")).exclude(n=DRILL_ITEMS)]
        self._row(f"bài thay thế không đủ {DRILL_ITEMS} câu", len(bad), 0)
        for b in bad:
            self._fail(b)
        bad = [f"chương {u.number}: {u.n} đoạn" for u in
               Unit.objects.annotate(n=Count("roleplays")).exclude(n=ROLEPLAYS_PER_UNIT)]
        self._row(f"chương không đủ {ROLEPLAYS_PER_UNIT} đoạn đóng vai", len(bad), 0)
        for b in bad:
            self._fail(b)

    def _blanks(self):
        """Tập {n} trong lời thoại phải khớp đúng tập RoleplayBlank.number của đoạn đó."""
        self.stdout.write(self.style.MIGRATE_HEADING("\n[3] Chỗ trống {n} ↔ đáp án"))
        lech = 0
        for rp in Roleplay.objects.select_related("unit").prefetch_related("lines", "blanks"):
            in_text = sorted(int(n) for line in rp.lines.all() for n in BLANK_RE.findall(line.text_jp))
            answers = sorted(b.number for b in rp.blanks.all())
            if in_text != answers:
                lech += 1
                self._fail(f"chương {rp.unit.number} đóng vai {rp.number}: "
                           f"lời thoại có {in_text}, đáp án có {answers}")
        self._row("đoạn đóng vai lệch chỗ trống", lech, 0)

    def _politeness(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[4] Câu theo mức lịch sự"))
        bad = []
        rows = Lesson.objects.annotate(
            n=Count("politeness_phrases"), levels=Count("politeness_phrases__level_code", distinct=True),
        ).filter(n__gt=0)
        for lesson in rows:
            if lesson.n != PHRASES_PER_LESSON or lesson.levels != PHRASES_PER_LESSON:
                bad.append(f"bài {lesson.scene_no}: {lesson.n} câu, {lesson.levels} mức")
        self._row(f"bài không đúng {PHRASES_PER_LESSON} câu khác mức", len(bad), 0)
        for b in bad:
            self._fail(b)

    def _empty(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[5] Dòng mồ côi / rỗng"))
        self._row("chương không có bài nào", Unit.objects.filter(lessons__isnull=True).count(), 0)
        self._row("đoạn đóng vai không có lời thoại", Roleplay.objects.filter(lines__isnull=True).count(), 0)
        self._row("đoạn đóng vai không có chỗ trống", Roleplay.objects.filter(blanks__isnull=True).count(), 0)
