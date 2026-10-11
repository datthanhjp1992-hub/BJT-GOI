"""
Test Sổ câu sai (T7.8) và báo lỗi câu đề thi (T7.11) — cần PostgreSQL.

Chạy: python manage.py test apps.exam.tests.test_wrongbook
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.constants import SESSION_TYPE_QUIZ, VOCAB_Q_MEANING, VOCAB_Q_READING
from apps.error_reports.models import ErrorReport
from apps.exam.models import ExamAttempt, ExamQuestion, WrongBookEntry
from apps.exam.services import attempts, wrongbook
from apps.exam.tests.test_mock import make_set
from apps.learning.models import StudySession
from apps.vocabulary.models import Topic, Vocabulary, VocabularyTopic

User = get_user_model()

WORDS = [("決裁", "けっさい", "Phê duyệt"), ("決済", "けっさい", "Thanh toán"), ("稟議書", "りんぎしょ", "Văn bản trình"),
         ("始末書", "しまつしょ", "Bản kiểm điểm"), ("顛末書", "てんまつしょ", "Bản tường trình"), ("アクセス", "アクセス", "Truy cập")]


class WrongbookTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.user = User.objects.create_user(username="nguoion", password="MatKhauRatManh123")
        cls.other = User.objects.create_user(username="nguoikhac", password="MatKhauRatManh123")
        topic = Topic.objects.create(name="Kế toán", slug="accounting-finance")
        cls.words = []
        for w, r, m in WORDS:
            v = Vocabulary.objects.create(word=w, reading=r, meaning_vi=m)
            VocabularyTopic.objects.create(vocabulary=v, topic=topic)
            cls.words.append(v)
        cls.exam_set = make_set()

    def setUp(self):
        self.client.force_login(self.user)

    def seed_book(self):
        wrongbook.record_wrong(self.user, vocabulary=self.words[0], question_type_code=VOCAB_Q_READING)
        wrongbook.record_wrong(self.user, vocabulary=self.words[5], question_type_code=VOCAB_Q_READING)  # kana -> đổi dạng
        for q in ExamQuestion.objects.filter(number__in=(1, 6)):
            wrongbook.record_wrong(self.user, question=q)

    def answer_all(self, attempt, correct):
        for ans in attempt.answers.select_related("question").prefetch_related("question__options"):
            if ans.question_id:
                right = ans.question.options.get(is_correct=True).position
            else:
                right = ans.payload["correct"]
            pick = right if correct else (right % 4) + 1
            attempts.answer(attempt, ans.order, pick)


class ServiceTests(WrongbookTestCase):
    def test_attempt_is_one_target_and_keeps_entry_ids(self):
        self.seed_book()
        vocab = attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_VOCAB, rng=random.Random(1)).attempt
        self.assertEqual(vocab.answers.count(), 2)
        self.assertTrue(attempts.is_vocab_attempt(vocab))
        kana = vocab.answers.get(vocabulary=self.words[5])
        self.assertEqual(kana.question_type_code, VOCAB_Q_MEANING)  # アクセス không hỏi cách đọc được
        self.assertTrue(all(a.payload.get("wrongbook_entry") for a in vocab.answers.all()))
        exam = attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_EXAM).attempt
        self.assertEqual(exam.answers.filter(question__isnull=False).count(), 2)
        self.assertFalse(attempts.is_vocab_attempt(exam))

    def test_two_correct_days_clear_entry_even_when_question_type_changed(self):
        self.seed_book()
        entry = WrongBookEntry.objects.get(vocabulary=self.words[5])
        attempt = attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_VOCAB).attempt
        self.answer_all(attempt, correct=True)
        entry.refresh_from_db()
        self.assertEqual((entry.correct_streak, entry.cleared_at), (1, None))
        self.assertFalse(WrongBookEntry.objects.filter(vocabulary=self.words[5], question_type_code=VOCAB_Q_MEANING).exists())

        attempts.finish(attempt)
        # Hôm nay đã đúng -> không được chọn lại hôm nay.
        self.assertIsNone(attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_VOCAB).attempt)

        WrongBookEntry.objects.update(last_correct_on=self.user.local_today() - timedelta(days=1))
        second = attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_VOCAB).attempt
        self.answer_all(second, correct=True)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.cleared_at)

    def test_wrong_resets_streak(self):
        self.seed_book()
        WrongBookEntry.objects.update(correct_streak=1, last_correct_on=self.user.local_today() - timedelta(days=1))
        attempt = attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_EXAM).attempt
        self.answer_all(attempt, correct=False)
        for e in WrongBookEntry.objects.filter(question__isnull=False):
            self.assertEqual((e.correct_streak, e.wrong_count), (0, 2))

    def test_wrongbook_attempt_not_counted_for_badges(self):
        self.seed_book()
        attempt = attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_EXAM).attempt
        self.answer_all(attempt, correct=True)
        self.assertTrue(attempts.finish(attempt))
        self.assertFalse(StudySession.objects.filter(user=self.user, session_type=SESSION_TYPE_QUIZ).exists())

    def test_resume_and_empty(self):
        self.assertIsNone(attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_VOCAB).attempt)
        self.seed_book()
        first = attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_VOCAB).attempt
        self.assertTrue(attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_VOCAB).resumed)
        self.assertNotEqual(attempts.start_wrongbook_attempt(self.user, wrongbook.TARGET_EXAM).attempt.pk, first.pk)


class ViewTests(WrongbookTestCase):
    def test_page_and_badge(self):
        self.seed_book()
        html = self.client.get(reverse("exam:wrongbook")).content.decode()
        self.assertIn("決裁", html)
        self.assertIn(reverse("exam:start_wrongbook", args=[wrongbook.TARGET_VOCAB]), html)
        self.assertIn('<span class="tag">4</span>', html)  # badge sidebar
        self.assertNotIn("稟議書", self.client.get(reverse("exam:wrongbook") + "?xem=de-thi").content.decode())

    def test_full_vocab_review_run(self):
        self.seed_book()
        response = self.client.post(reverse("exam:start_wrongbook", args=[wrongbook.TARGET_VOCAB]))
        attempt = ExamAttempt.objects.get(user=self.user)
        self.assertRedirects(response, reverse("exam:play", args=[attempt.pk]))
        self.assertContains(self.client.get(reverse("exam:play", args=[attempt.pk])), 'id="exam-play"')
        self.answer_all(attempt, correct=True)
        self.client.post(reverse("exam:finish", args=[attempt.pk]))
        html = self.client.get(reverse("exam:result", args=[attempt.pk])).content.decode()
        self.assertIn(reverse("exam:wrongbook"), html)

    def test_exam_review_run_uses_exam_screens(self):
        self.seed_book()
        self.client.post(reverse("exam:start_wrongbook", args=[wrongbook.TARGET_EXAM]))
        attempt = ExamAttempt.objects.get(user=self.user)
        html = self.client.get(reverse("exam:play", args=[attempt.pk])).content.decode()
        self.assertIn("ex-exam-bar", html)
        self.assertNotIn("data-seconds-left", html)  # ôn sổ không bấm giờ

    def test_nothing_due_redirects_back(self):
        response = self.client.post(reverse("exam:start_wrongbook", args=[wrongbook.TARGET_EXAM]))
        self.assertRedirects(response, reverse("exam:wrongbook"))

    def test_other_user_cannot_see_entries(self):
        self.seed_book()
        self.client.force_login(self.other)
        self.assertNotIn("決裁", self.client.get(reverse("exam:wrongbook")).content.decode())


class ErrorReportTests(WrongbookTestCase):
    def test_report_exam_question(self):
        q = ExamQuestion.objects.get(number=1)
        url = reverse("error_reports:create") + f"?exam_question={q.pk}"
        self.assertContains(self.client.get(url), q.stem_jp)
        error_type = __import__("apps.core.constants", fromlist=["error_type_choices"]).error_type_choices()[0][0]
        self.client.post(reverse("error_reports:create"), {
            "exam_question": q.pk, "error_type_code": error_type, "description": "Đáp án câu này có vẻ sai.",
        })
        report = ErrorReport.objects.get()
        self.assertEqual(report.exam_question, q)
        self.assertIsNone(report.vocabulary)
        q.delete()
        report.refresh_from_db()
        self.assertIsNone(report.exam_question)  # SET_NULL: báo lỗi vẫn còn

    def test_result_page_links_to_report(self):
        attempt = attempts.start_mock_attempt(self.user, self.exam_set, "practice").attempt
        attempts.finish(attempt, force=True)
        q = ExamQuestion.objects.get(number=1)
        self.assertContains(self.client.get(reverse("exam:result", args=[attempt.pk])),
                            f"?exam_question={q.pk}")
