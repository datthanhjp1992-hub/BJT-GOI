"""Hậu kiểm dữ liệu kính ngữ sau khi nạp. KHÔNG ghi gì vào DB.

    python manage.py check_keigo_data --settings=config.settings.supabase

Vì sao cần lệnh này chứ không chỉ dựa vào `full_clean()` lúc nhập: ràng buộc ở
model chỉ soát được TỪNG DÒNG, không soát được "bộ đề này thiếu 3 câu" hay
"tổng phải là 262". Đúng loại lỗi đã lọt qua ở giai đoạn bóc dữ liệu — bảng tự
kiểm báo "khớp" trong khi thiếu hẳn 34 dòng.

Số liệu kỳ vọng lấy từ chính cuốn sách (đã đối chiếu tay với bảng đáp án
trang 52-54). Sửa nội dung thì sửa luôn EXPECTED bên dưới, đừng nới lỏng phép kiểm.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.core.constants import (
    QUESTION_TYPE_CLOZE,
    QUESTION_TYPE_ORDERING,
)
from apps.keigo.models import (
    ExerciseSection,
    ExerciseSet,
    KeigoExample,
    KeigoForm,
    KeigoLesson,
    KeigoPattern,
    KeigoPhrasePair,
    KeigoVerb,
    Question,
    QuestionOption,
)

EXPECTED = {
    "lesson": 7,
    "verb": 47,
    "form": 175,
    "pattern": 39,
    "example": 101,
    "phrase_pair": 87,
    "exercise_set": 17,
    "question": 262,
    "ordering": 34,
    "cloze": 5,
}


class Command(BaseCommand):
    help = "Hậu kiểm dữ liệu kính ngữ (chỉ đọc)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-expected", action="store_true",
            help="Bỏ qua phần đối chiếu với số liệu kỳ vọng của sách, chỉ soát tính nhất quán.",
        )

    def handle(self, *args, **options):
        self.failures = []
        self._counts(skip_expected=options["no_expected"])
        self._per_set()
        self._options()
        self._ordering()
        self._empty()

        self.stdout.write("")
        if self.failures:
            self.stdout.write(self.style.ERROR(f"CÓ {len(self.failures)} VẤN ĐỀ:"))
            for f in self.failures:
                self.stdout.write(self.style.ERROR(f"  - {f}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Tất cả phép kiểm đều đạt."))

    # -- helpers -----------------------------------------------------------

    def _fail(self, msg):
        self.failures.append(msg)

    def _row(self, label, got, want=None):
        if want is None:
            self.stdout.write(f"  {label:<28} {got}")
            return
        ok = got == want
        mark = self.style.SUCCESS("OK") if ok else self.style.ERROR("LỆCH")
        self.stdout.write(f"  {label:<28} {got:>5} / kỳ vọng {want:<5} {mark}")
        if not ok:
            self._fail(f"{label}: có {got}, kỳ vọng {want}")

    # -- các phép kiểm -----------------------------------------------------

    def _counts(self, skip_expected):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[1] Số dòng từng bảng"))
        got = {
            "lesson": KeigoLesson.objects.count(),
            "verb": KeigoVerb.objects.count(),
            "form": KeigoForm.objects.count(),
            "pattern": KeigoPattern.objects.count(),
            "example": KeigoExample.objects.count(),
            "phrase_pair": KeigoPhrasePair.objects.count(),
            "exercise_set": ExerciseSet.objects.count(),
            "question": Question.objects.count(),
            "ordering": Question.objects.filter(question_type=QUESTION_TYPE_ORDERING).count(),
            "cloze": Question.objects.filter(question_type=QUESTION_TYPE_CLOZE).count(),
        }
        for k, v in got.items():
            self._row(k, v, None if skip_expected else EXPECTED[k])
        self._row("question_option", QuestionOption.objects.count())

    def _per_set(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n[2] question_count (đếm từ bảng đáp án) vs số câu thật"
        ))
        rows = (
            ExerciseSet.objects.annotate(actual=Count("sections__questions"))
            .order_by("display_order")
        )
        for s in rows:
            ok = s.actual == s.question_count
            mark = self.style.SUCCESS("OK") if ok else self.style.ERROR("LỆCH")
            self.stdout.write(
                f"  {s.slug:<14} khai {s.question_count:>3}  thật {s.actual:>3}  {mark}"
            )
            if not ok:
                self._fail(
                    f"{s.slug}: question_count={s.question_count} nhưng có {s.actual} câu thật"
                )

    def _options(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[3] Mỗi câu đúng MỘT phương án đúng"))
        rows = Question.objects.annotate(
            n_opt=Count("options", distinct=True),
            n_ok=Count("options", filter=Q(options__is_correct=True), distinct=True),
        )
        bad_zero = [q.code for q in rows if q.n_ok == 0]
        bad_many = [q.code for q in rows if q.n_ok > 1]
        no_opt = [q.code for q in rows if q.n_opt == 0]
        self._row("câu không có đáp án đúng", len(bad_zero), 0)
        self._row("câu có >1 đáp án đúng", len(bad_many), 0)
        self._row("câu không có phương án nào", len(no_opt), 0)
        for code in (bad_zero + bad_many + no_opt)[:20]:
            self.stdout.write(self.style.WARNING(f"      {code}"))

    def _ordering(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n[4] Kiểm chéo ★: correct_order[star_position-1] == phương án đúng"
        ))
        checked = lech = 0
        for q in Question.objects.filter(
            question_type=QUESTION_TYPE_ORDERING
        ).prefetch_related("options"):
            expect = q.expected_correct_position()
            if expect is None:
                self._fail(f"{q.code}: star_position/correct_order sai định dạng "
                           f"(star={q.star_position}, order='{q.correct_order}')")
                lech += 1
                continue
            marked = [o.position for o in q.options.all() if o.is_correct]
            checked += 1
            if len(marked) != 1 or marked[0] != expect:
                lech += 1
                self._fail(
                    f"{q.code}: ★ ở vị trí {q.star_position}, order='{q.correct_order}' "
                    f"=> phải là phương án {expect}, đang đánh {marked or 'không có'}"
                )
        self.stdout.write(f"  Đã kiểm {checked} câu sắp xếp, lệch {lech}.")

    def _empty(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n[5] Dòng mồ côi / rỗng"))
        self._row("bộ đề không có phần đề nào",
                  ExerciseSet.objects.filter(sections__isnull=True).count(), 0)
        self._row("phần đề không có câu nào",
                  ExerciseSection.objects.filter(questions__isnull=True).count(), 0)
        self._row("mẫu ngữ pháp không có ví dụ",
                  KeigoPattern.objects.filter(examples__isnull=True).count(), 0)
        self._row("động từ không có dạng nào",
                  KeigoVerb.objects.filter(forms__isnull=True).count(), 0)
        self._row("câu cloze không có đoạn văn",
                  Question.objects.filter(
                      question_type=QUESTION_TYPE_CLOZE, section__passage_jp=""
                  ).count(), 0)
