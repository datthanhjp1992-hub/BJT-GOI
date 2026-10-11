"""
Test thi thử / luyện dạng đề (mốc 2 — T7.6, T7.7) — cần PostgreSQL.

Chạy: python manage.py test apps.exam.tests.test_mock
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import EXAM_MODE_EXAM, EXAM_MODE_PRACTICE, SESSION_TYPE_QUIZ
from apps.exam.models import ExamAnswer, ExamAttempt, ExamOption, ExamQuestion, ExamSet, WrongBookEntry
from apps.exam.services import attempts
from apps.learning.models import StudySession, UserVocabularyProgress
from apps.vocabulary.models import Vocabulary

User = get_user_model()

# (section, passage_type, passage, audio) — 3 câu Nghe, 2 câu Nghe+Đọc, 3 câu Đọc.
LAYOUT = [
    ("p1s1", "会話", "A：会議室の鍵をお借りしたいんですが。", "mock/q1.mp3"),
    ("p1s2", "場面設定", "取引先の担当者が到着しました。", "mock/q2.mp3"),
    ("p1s3", "会話", "A：見積書を確認しました。", "mock/q3.mp3"),
    ("p2s2", "スケジュール表", "【本日の会議】10:00 開会", ""),
    ("p2s2", "価格表", "【料金】Aルーム 3,000円", ""),
    ("p3s1", "", "", ""),
    ("p3s1", "", "", ""),
    ("p3s3", "社内文書", "社員各位 来月より予約システムを使用します。", ""),
]


def make_set(number=1):
    exam_set = ExamSet.objects.create(number=number, title=f"Bộ đề {number}", slug=f"bo-de-{number}")
    for i, (section, ptype, passage, audio) in enumerate(LAYOUT, start=1):
        q = ExamQuestion.objects.create(
            exam_set=exam_set, part=int(section[1]), section_code=section, number=i, passage_type=ptype,
            passage_jp=passage, stem_jp=f"決算報告の問題{number}-{i}", audio_path=audio,
            explanation_vi=f"Giải thích {i}", source_ref=f"t:{number}:{i}",
        )
        for pos in range(1, 5):
            ExamOption.objects.create(question=q, position=pos, text_jp=f"選択肢{pos}", is_correct=pos == 1)
    return exam_set


class MockTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.user = User.objects.create_user(username="nguoithi", password="MatKhauRatManh123")
        cls.other = User.objects.create_user(username="nguoikhac", password="MatKhauRatManh123")
        cls.exam_set = make_set()
        cls.vocab = Vocabulary.objects.create(word="決算報告", reading="けっさんほうこく", meaning_vi="Báo cáo quyết toán")

    def setUp(self):
        self.client.force_login(self.user)

    def start(self, mode=EXAM_MODE_EXAM):
        return attempts.start_mock_attempt(self.user, self.exam_set, mode).attempt

    def order_of(self, attempt, number):
        return attempt.answers.get(question__number=number).order


class TimedFlowTests(MockTestCase):
    def test_start_creates_all_questions_and_opens_part_1(self):
        attempt = self.start()
        self.assertEqual(attempt.answers.count(), 8)
        self.assertEqual(attempt.current_part, 1)
        self.assertIn("1", attempt.part_started_at)
        self.assertTrue(attempts.start_mock_attempt(self.user, self.exam_set, EXAM_MODE_PRACTICE).resumed)

    def test_listening_is_one_way(self):
        attempt = self.start()
        q1, q2, q3 = (self.order_of(attempt, n) for n in (1, 2, 3))
        self.assertIsNone(attempts.answer(attempt, q2, 1))          # chưa tới câu 2
        self.assertTrue(attempts.answer(attempt, q1, 2).first_time)  # sai
        attempt.refresh_from_db()
        self.assertEqual(attempts.cursor(attempt), q2)
        self.assertIsNone(attempts.answer(attempt, q1, 1))          # câu đã qua khoá
        attempts.skip(attempt, q2)
        attempt.refresh_from_db()
        self.assertEqual(attempts.cursor(attempt), q3)
        attempts.answer(attempt, q3, 1)                              # câu cuối phần Nghe -> sang phần 2
        attempt.refresh_from_db()
        self.assertEqual(attempt.current_part, 2)
        self.assertIn("1", attempt.part_submitted_at)

    def test_reading_parts_allow_changing_answers_until_submitted(self):
        attempt = self.start()
        attempts.submit_part(attempt)
        q4 = self.order_of(attempt, 4)
        attempts.answer(attempt, q4, 2)
        attempts.answer(attempt, q4, 1)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 1)
        attempts.submit_part(attempt)
        self.assertIsNone(attempts.answer(attempt, q4, 3))          # phần 2 đã nộp
        self.assertEqual(attempt.current_part, 3)

    def test_time_up_submits_parts_and_finishes(self):
        attempt = self.start()
        attempts.submit_part(attempt)
        attempts.answer(attempt, self.order_of(attempt, 4), 1)
        attempts.submit_part(attempt)
        later = timezone.now() + timedelta(hours=3)
        attempts.refresh_timing(attempt, now=later)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_finished)
        self.assertEqual((attempt.score, attempt.total), (1, 8))
        # 7 câu sai / bỏ trống vào sổ lúc nộp; phiên quiz cho streak + danh hiệu.
        self.assertEqual(WrongBookEntry.objects.filter(user=self.user).count(), 7)
        self.assertTrue(StudySession.objects.filter(user=self.user, session_type=SESSION_TYPE_QUIZ).exists())

    def test_no_wrongbook_before_submit_in_exam_mode(self):
        attempt = self.start()
        attempts.answer(attempt, self.order_of(attempt, 1), 2)
        self.assertFalse(WrongBookEntry.objects.exists())


class PracticeFlowTests(MockTestCase):
    def test_practice_mock_is_free_and_immediate(self):
        attempt = self.start(EXAM_MODE_PRACTICE)
        q3 = self.order_of(attempt, 3)
        result = attempts.answer(attempt, q3, 2)                     # nhảy thẳng câu 3
        self.assertTrue(result.first_time)
        self.assertFalse(attempts.answer(attempt, q3, 1).first_time)  # không ghi đè
        self.assertTrue(WrongBookEntry.objects.filter(question__number=3).exists())
        self.assertFalse(attempts.finish(attempt))                   # chưa làm hết

    def test_drill_prefers_unseen_questions(self):
        make_set(2)
        first = attempts.start_drill_attempt(self.user, "p3s1", rng=random.Random(1)).attempt
        self.assertEqual(first.total, 4)  # 2 bộ đề × 2 câu p3s1
        for ans in first.answers.all()[:2]:
            attempts.answer(first, ans.order, 1)
        seen = set(first.answers.filter(selected__isnull=False).values_list("question_id", flat=True))
        first.delete()
        again = attempts.start_drill_attempt(self.user, "p3s1", rng=random.Random(2)).attempt
        first_two = list(again.answers.order_by("order").values_list("question_id", flat=True))[:2]
        self.assertFalse(seen & set(first_two))
        self.assertTrue(attempts.start_drill_attempt(self.user, "p3s1").resumed)


@override_settings(EXAM_AUDIO_BASE_URL="https://x.supabase.co/storage/v1/object/public/exam-audio/")
class ViewTests(MockTestCase):
    def test_exam_list_and_start(self):
        self.assertContains(self.client.get(reverse("exam:exams")), "Bộ đề 1")
        response = self.client.post(reverse("exam:start_mock", args=["bo-de-1"]), {"mode": EXAM_MODE_EXAM})
        attempt = ExamAttempt.objects.get(user=self.user)
        self.assertRedirects(response, reverse("exam:play", args=[attempt.pk]))
        self.assertEqual(attempt.mode_code, EXAM_MODE_EXAM)

    def test_exam_mode_hides_transcript_but_shows_audio(self):
        attempt = self.start()
        html = self.client.get(reverse("exam:play", args=[attempt.pk])).content.decode()
        self.assertNotIn("会議室の鍵をお借りしたい", html)
        self.assertIn("mock/q1.mp3?v=1", html)
        self.assertIn("data-audio-once", html)
        self.assertIn("data-seconds-left", html)

    def test_scene_and_documents_are_visible(self):
        attempt = self.start()
        attempts.answer(attempt, self.order_of(attempt, 1), 1)
        html = self.client.get(reverse("exam:play", args=[attempt.pk])).content.decode()
        self.assertIn("取引先の担当者が到着しました", html)  # 場面設定 hiện cùng câu hỏi
        attempts.submit_part(attempt)
        html = self.client.get(reverse("exam:play", args=[attempt.pk])).content.decode()
        self.assertIn("【本日の会議】", html)

    def test_practice_feedback_shows_transcript_and_explanation(self):
        attempt = self.start(EXAM_MODE_PRACTICE)
        url = reverse("exam:play", args=[attempt.pk])
        response = self.client.post(url, {"order": 1, "option": 2})
        self.assertRedirects(response, url + "?da=1")
        html = self.client.get(url + "?da=1").content.decode()
        self.assertIn("会議室の鍵をお借りしたい", html)
        self.assertIn("Giải thích 1", html)

    def test_locked_answer_flashes_and_listening_advances(self):
        attempt = self.start()
        url = reverse("exam:play", args=[attempt.pk])
        self.client.post(url, {"order": 1, "option": 1})
        self.client.post(url, {"order": 1, "option": 2})  # câu đã qua
        self.assertTrue(ExamAnswer.objects.get(attempt=attempt, order=1).is_correct)
        self.client.post(url, {"order": 2, "action": "skip"})
        attempt.refresh_from_db()
        self.assertEqual(attempts.cursor(attempt), 3)

    def test_submit_part_view_and_result(self):
        attempt = self.start()
        for _ in range(3):
            self.client.post(reverse("exam:submit_part", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_finished)
        response = self.client.get(reverse("exam:result", args=[attempt.pk]))
        self.assertContains(response, "0%")
        self.assertContains(response, "Nắm bắt ngữ cảnh")
        self.assertContains(response, "決算報告")  # gợi ý thêm từ

    def test_add_words_only_accepts_suggested(self):
        attempt = self.start()
        attempts.finish(attempt, force=True)
        other_word = Vocabulary.objects.create(word="無関係", reading="むかんけい", meaning_vi="x")
        self.client.post(reverse("exam:add_words", args=[attempt.pk]), {"words": [self.vocab.pk, other_word.pk]})
        learned = set(UserVocabularyProgress.objects.filter(user=self.user).values_list("vocabulary_id", flat=True))
        self.assertEqual(learned, {self.vocab.pk})

    def test_other_user_gets_404(self):
        attempt = self.start()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("exam:play", args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("exam:submit_part", args=[attempt.pk])).status_code, 404)

    def test_hub_shows_drill_weak_spot(self):
        make_set(2)
        make_set(3)  # 3 bộ × 2 câu p3s1 = 6 câu, đủ ngưỡng 5 câu để thành "dạng yếu"
        attempt = attempts.start_drill_attempt(self.user, "p3s1").attempt
        for ans in attempt.answers.all():
            attempts.answer(attempt, ans.order, 2)
        other = attempts.start_drill_attempt(self.other, "p3s1").attempt  # người khác không tính
        attempts.answer(other, 1, 1)
        html = self.client.get(reverse("exam:hub")).content.decode()
        self.assertIn(reverse("exam:start_drill", args=["p3s1"]), html)
        self.assertIn("0%", html)
