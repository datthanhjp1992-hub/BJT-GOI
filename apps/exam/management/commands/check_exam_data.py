"""
Soát dữ liệu đề thi trong DB — docs/SPEC_KIEM_TRA.md T7.2.

    python manage.py check_exam_data
    python manage.py check_exam_data --audio   # kiểm thêm file audio có trên bucket (HEAD từng URL)

Báo: câu không đủ 4 phương án / không đúng 1 đáp án, câu nghe thiếu audio_path,
bộ đề lệch số câu theo dạng (chuẩn 10/10/15 · 15/15 · 15/10/10). Câu is_active=False bỏ qua.
"""
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from apps.exam.audio import exam_audio_url
from apps.exam.importer import check_database
from apps.exam.models import ExamQuestion


class Command(BaseCommand):
    help = "Soát dữ liệu đề thi thử."

    def add_arguments(self, parser):
        parser.add_argument("--audio", action="store_true", help="Kiểm file audio trên bucket (cần mạng).")

    def handle(self, *args, **options):
        problems = check_database()
        if options["audio"]:
            problems += self._check_audio()
        total = ExamQuestion.objects.filter(is_active=True).count()
        if problems:
            for p in problems:
                self.stdout.write(self.style.ERROR(f"  {p}"))
            raise CommandError(f"{len(problems)} lỗi trong {total} câu đang dùng.")
        self.stdout.write(self.style.SUCCESS(f"Dữ liệu đề ổn — {total} câu đang dùng."))

    def _check_audio(self):
        problems = []
        questions = ExamQuestion.objects.filter(is_active=True).exclude(audio_path="")
        for q in questions:
            url = exam_audio_url(q)
            if not url:
                return ["Chưa cấu hình EXAM_AUDIO_BASE_URL — không kiểm được audio."]
            try:
                urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=15)
            except urllib.error.HTTPError as e:
                problems.append(f"{q.exam_set_id}-{q.number}: audio HTTP {e.code} ({q.audio_path})")
            except urllib.error.URLError as e:
                problems.append(f"{q.exam_set_id}-{q.number}: không tải được audio ({e.reason})")
        return problems
