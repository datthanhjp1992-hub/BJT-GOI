"""
Test nhập đề thi (apps/exam/importer.py, T7.2) — cần PostgreSQL.

Chạy: python manage.py test apps.exam.tests.test_importer
"""
from django.core.management import call_command
from django.test import TestCase

from apps.exam import importer
from apps.exam.models import ExamOption, ExamQuestion, ExamSet


def row(ref, number, section="p3s1", correct="2", **extra):
    base = {
        "source_ref": f"bjt.db:mock_exam_question:{ref}", "exam_set": "1", "number": str(number),
        "part": section[1], "section_code": section, "passage_type": "", "passage_jp": "",
        "stem_jp": f"問題{ref}", "option_1": "あ", "option_2": "い", "option_3": "う", "option_4": "え",
        "correct": correct, "explanation_vi": "giải thích", "level": "N2", "audio_path": "", "source_note": "Q8",
    }
    base.update(extra)
    return base


class ImporterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def test_validate_catches_bad_rows(self):
        bad = [row(1, 1, correct="5"), row(2, 2, option_3="あ"), row(3, 3, section="p9s1"), row(3, 4)]
        messages = " | ".join(m for _, m in importer.validate(bad))
        self.assertIn("correct", messages)
        self.assertIn("trùng nhau", messages)
        self.assertIn("section_code", messages)
        self.assertIn("source_ref trùng", messages)
        self.assertEqual(importer.validate([row(1, 1), row(2, 2)]), [])

    def test_apply_is_idempotent(self):
        rows = [row(1, 1), row(2, 2, section="p1s1", audio_path="mock/q002.mp3")]
        first = importer.apply_rows(rows)
        self.assertEqual((first.sets_new, first.new), (1, 2))
        self.assertEqual(ExamOption.objects.filter(is_correct=True).count(), 2)
        again = importer.apply_rows(rows)
        self.assertEqual((again.new, again.updated, again.same), (0, 0, 2))

    def test_update_keeps_is_active_and_audio_version(self):
        importer.apply_rows([row(1, 1)])
        ExamQuestion.objects.update(is_active=False, audio_version=4)
        stats = importer.apply_rows([row(1, 1, correct="3", stem_jp="問題1（改）")])
        self.assertEqual(stats.updated, 1)
        q = ExamQuestion.objects.get()
        self.assertEqual((q.stem_jp, q.is_active, q.audio_version), ("問題1（改）", False, 4))
        self.assertEqual(q.options.get(is_correct=True).position, 3)

    def test_swapping_numbers_does_not_hit_unique_constraint(self):
        importer.apply_rows([row(1, 1), row(2, 2)])
        importer.apply_rows([row(1, 2), row(2, 1)])
        self.assertEqual(ExamQuestion.objects.get(source_ref__endswith=":1").number, 2)
        self.assertEqual(ExamQuestion.objects.get(source_ref__endswith=":2").number, 1)

    def test_check_database_reports_wrong_section_counts_and_missing_audio(self):
        importer.apply_rows([row(1, 1, section="p1s1")])
        problems = " | ".join(importer.check_database())
        self.assertIn("thiếu audio_path", problems)
        self.assertIn("số câu theo dạng", problems)
        self.assertEqual(ExamSet.objects.count(), 1)

    def test_transcript_vs_scene(self):
        importer.apply_rows([row(1, 1, section="p1s1", passage_type="会話", audio_path="mock/a.mp3"),
                             row(2, 2, section="p1s2", passage_type="場面設定", audio_path="mock/b.mp3"),
                             row(3, 3, section="p3s3", passage_type="社内文書")])
        q1, q2, q3 = ExamQuestion.objects.order_by("number")
        self.assertTrue(q1.passage_is_transcript)
        self.assertFalse(q2.passage_is_transcript)
        self.assertFalse(q3.passage_is_transcript)
