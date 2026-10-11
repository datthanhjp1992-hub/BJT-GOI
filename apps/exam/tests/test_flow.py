"""
Test luồng bài Kiểm tra từ vựng (mốc 1) — cần PostgreSQL (pg_trgm) như mọi test có DB của dự án.

Chạy: python manage.py test apps.exam
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import (
    EXAM_KIND_VOCAB,
    SESSION_TYPE_QUIZ,
    VOCAB_Q_MEANING,
    VOCAB_Q_READING,
    VOCAB_Q_WORD,
)
from apps.exam.constants import SCOPE_DUE, SCOPE_MASTERED, SCOPE_TOPICS
from apps.exam.models import ExamAnswer, ExamAttempt, WrongBookEntry
from apps.exam.services import attempts, wrongbook
from apps.learning import srs
from apps.learning.models import StudySession, UserVocabularyProgress
from apps.vocabulary.models import ExampleSentence, Topic, Vocabulary, VocabularyTopic

User = get_user_model()

WORDS = [
    ("決裁", "けっさい", "Phê duyệt"),
    ("決済", "けっさい", "Thanh toán"),
    ("稟議書", "りんぎしょ", "Văn bản trình xin phê duyệt"),
    ("始末書", "しまつしょ", "Bản kiểm điểm"),
    ("顛末書", "てんまつしょ", "Bản tường trình"),
    ("委任状", "いにんじょう", "Giấy uỷ quyền"),
    ("資金繰り", "しきんぐり", "Xoay vòng vốn"),
    ("アクセス", "アクセス", "Truy cập"),
]


class ExamTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.user = User.objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        cls.other = User.objects.create_user(username="nguoikhac", password="MatKhauRatManh123")
        cls.topic = Topic.objects.create(name="Kế toán", slug="accounting-finance")
        cls.line = Topic.objects.create(name="Ke-Line", slug="ke-line")
        cls.words = []
        for word, reading, meaning in WORDS:
            v = Vocabulary.objects.create(word=word, reading=reading, meaning_vi=meaning)
            VocabularyTopic.objects.create(vocabulary=v, topic=cls.topic)
            cls.words.append(v)
        ExampleSentence.objects.create(vocabulary=cls.words[0], sentence_jp="部長の決裁を仰ぐ。",
                                       sentence_vi="Xin trưởng phòng phê duyệt.")
        today = cls.user.local_today()
        for i, v in enumerate(cls.words):
            UserVocabularyProgress.objects.create(
                user=cls.user, vocabulary=v, card_state=srs.REVIEW, interval_days=30 if i < 5 else 3,
                next_review_date=today - timedelta(days=1) if i < 6 else today + timedelta(days=5),
                is_mastered=i < 5,
            )

    def setUp(self):
        self.client.force_login(self.user)

    def start(self, scope=SCOPE_TOPICS, types=(VOCAB_Q_MEANING, VOCAB_Q_WORD, VOCAB_Q_READING), count=8, srs_link=True):
        return attempts.start_vocab_attempt(
            self.user, scope=scope, topic_ids=[self.topic.pk], types=types, count=count,
            srs_link=srs_link, rng=random.Random(7),
        )

    def progress(self, vocab):
        return UserVocabularyProgress.objects.get(user=self.user, vocabulary=vocab)

    def answer_wrong(self, attempt, ans):
        wrong = next(i for i in range(1, len(ans.payload["options"]) + 1) if i != ans.payload["correct"])
        return attempts.answer(attempt, ans.order, wrong)


class StartTests(ExamTestCase):
    def test_creates_all_questions_up_front(self):
        result = self.start()
        attempt = result.attempt
        self.assertFalse(result.resumed)
        self.assertEqual(attempt.total, 8)
        self.assertEqual(attempt.answers.count(), 8)
        for ans in attempt.answers.all():
            options = [o["text"] for o in ans.payload["options"]]
            self.assertEqual(len(options), len(set(options)))
            self.assertTrue(1 <= ans.payload["correct"] <= len(options))
            if ans.question_type_code == VOCAB_Q_READING:
                self.assertNotEqual(ans.vocabulary.word, "アクセス")

    def test_meaning_distractor_never_equals_correct_meaning(self):
        attempt = self.start(types=(VOCAB_Q_MEANING,)).attempt
        for ans in attempt.answers.all():
            texts = [o["text"] for o in ans.payload["options"]]
            self.assertEqual(texts.count(ans.vocabulary.meaning_vi), 1)

    def test_second_start_resumes(self):
        first = self.start().attempt
        again = self.start()
        self.assertTrue(again.resumed)
        self.assertEqual(again.attempt.pk, first.pk)
        self.assertEqual(ExamAttempt.objects.filter(user=self.user).count(), 1)

    def test_not_enough_words(self):
        UserVocabularyProgress.objects.filter(user=self.user).exclude(vocabulary__in=self.words[:3]).delete()
        result = self.start()
        self.assertIsNone(result.attempt)
        self.assertEqual(result.not_enough, 3)

    def test_due_scope_takes_only_due_review_words(self):
        attempt = self.start(scope=SCOPE_DUE).attempt
        self.assertEqual(set(attempt.answers.values_list("vocabulary_id", flat=True)),
                         {v.pk for v in self.words[:6]})

    def test_mastered_scope(self):
        attempt = self.start(scope=SCOPE_MASTERED).attempt
        self.assertEqual(attempt.answers.count(), 5)


class AnswerTests(ExamTestCase):
    def test_score_and_no_double_grading(self):
        attempt = self.start().attempt
        ans = attempt.answers.get(order=1)
        first = attempts.answer(attempt, 1, ans.payload["correct"])
        self.assertTrue(first.first_time)
        self.assertTrue(first.answer.is_correct)
        again = self.answer_wrong(attempt, ans)  # F5 / bấm lại lựa chọn khác
        self.assertFalse(again.first_time)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 1)
        self.assertTrue(attempt.answers.get(order=1).is_correct)

    def test_out_of_range_option_rejected(self):
        attempt = self.start().attempt
        self.assertIsNone(attempts.answer(attempt, 1, 9))
        self.assertIsNone(attempts.answer(attempt, 99, 1))

    def test_wrong_answer_sends_word_to_relearn_and_wrongbook(self):
        attempt = self.start().attempt
        ans = attempt.answers.get(order=1)
        result = self.answer_wrong(attempt, ans)
        self.assertEqual(result.srs_effect, "relearn")
        self.assertEqual(self.progress(ans.vocabulary).card_state, srs.RELEARNING)
        self.assertTrue(WrongBookEntry.objects.filter(user=self.user, vocabulary=ans.vocabulary,
                                                      question_type_code=ans.question_type_code).exists())

    def test_srs_link_off_leaves_schedule_alone(self):
        attempt = self.start(srs_link=False).attempt
        ans = attempt.answers.get(order=1)
        before = self.progress(ans.vocabulary)
        result = self.answer_wrong(attempt, ans)
        self.assertIsNone(result.srs_effect)
        after = self.progress(ans.vocabulary)
        self.assertEqual((after.card_state, after.next_review_date), (before.card_state, before.next_review_date))

    def test_correct_due_word_counts_as_review(self):
        attempt = self.start(scope=SCOPE_DUE).attempt
        ans = attempt.answers.get(order=1)
        result = attempts.answer(attempt, 1, ans.payload["correct"])
        self.assertEqual(result.srs_effect, "reviewed")
        self.assertGreater(self.progress(ans.vocabulary).next_review_date, self.user.local_today())

    def test_correct_answer_outside_due_scope_does_not_touch_schedule(self):
        attempt = self.start(scope=SCOPE_TOPICS).attempt
        ans = attempt.answers.get(order=1)
        before = self.progress(ans.vocabulary).next_review_date
        result = attempts.answer(attempt, 1, ans.payload["correct"])
        self.assertIsNone(result.srs_effect)
        self.assertEqual(self.progress(ans.vocabulary).next_review_date, before)


class FinishTests(ExamTestCase):
    def test_cannot_finish_with_unanswered(self):
        attempt = self.start().attempt
        self.assertFalse(attempts.finish(attempt))

    def test_finish_records_quiz_session(self):
        attempt = self.start(count=4).attempt
        for ans in attempt.answers.all():
            attempts.answer(attempt, ans.order, ans.payload["correct"])
        self.assertTrue(attempts.finish(attempt))
        attempt.refresh_from_db()
        self.assertEqual((attempt.score, attempt.total), (4, 4))
        session = StudySession.objects.get(user=self.user, session_type=SESSION_TYPE_QUIZ)
        self.assertEqual((session.words_reviewed, session.correct_answers), (4, 4))
        self.assertIsNone(attempts.answer(attempt, 1, 1))  # đã nộp thì không chấm thêm


class WrongBookTests(ExamTestCase):
    def test_clears_after_two_correct_days(self):
        v = self.words[0]
        wrongbook.record_wrong(self.user, vocabulary=v, question_type_code=VOCAB_Q_READING)
        wrongbook.record_wrong(self.user, vocabulary=v, question_type_code=VOCAB_Q_READING)
        entry = WrongBookEntry.objects.get(user=self.user, vocabulary=v)
        self.assertEqual(entry.wrong_count, 2)

        wrongbook.record_right(self.user, vocabulary=v, question_type_code=VOCAB_Q_READING)
        wrongbook.record_right(self.user, vocabulary=v, question_type_code=VOCAB_Q_READING)  # cùng ngày
        entry.refresh_from_db()
        self.assertEqual(entry.correct_streak, 1)
        self.assertIsNone(entry.cleared_at)

        WrongBookEntry.objects.filter(pk=entry.pk).update(last_correct_on=self.user.local_today() - timedelta(days=1))
        wrongbook.record_right(self.user, vocabulary=v, question_type_code=VOCAB_Q_READING)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.cleared_at)
        self.assertEqual(wrongbook.open_count(self.user), 0)

        wrongbook.record_wrong(self.user, vocabulary=v, question_type_code=VOCAB_Q_READING)
        entry.refresh_from_db()
        self.assertIsNone(entry.cleared_at)
        self.assertEqual(entry.correct_streak, 0)

    def test_entry_needs_exactly_one_target(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            WrongBookEntry.objects.create(user=self.user, last_wrong_at=timezone.now())


class ViewTests(ExamTestCase):
    def test_login_required(self):
        self.client.logout()
        url = reverse("exam:hub")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_hub_and_setup_render_without_attempts(self):
        self.assertEqual(self.client.get(reverse("exam:hub")).status_code, 200)
        response = self.client.get(reverse("exam:vocab"))
        self.assertContains(response, self.topic.name)
        self.assertNotContains(response, self.line.name)  # topic hàng kana không hiện

    def test_setup_post_starts_attempt(self):
        response = self.client.post(reverse("exam:vocab"), {
            "scope": SCOPE_TOPICS, "topics": [str(self.topic.pk)], "types": [VOCAB_Q_MEANING],
            "count": "10", "srs_link": "on",
        })
        attempt = ExamAttempt.objects.get(user=self.user, kind_code=EXAM_KIND_VOCAB)
        self.assertRedirects(response, reverse("exam:play", args=[attempt.pk]))
        self.assertTrue(attempt.scope["srs_link"])

    def test_setup_requires_topics_for_topic_scope(self):
        response = self.client.post(reverse("exam:vocab"), {
            "scope": SCOPE_TOPICS, "types": [VOCAB_Q_MEANING], "count": "10",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ExamAttempt.objects.exists())

    def test_other_users_attempt_is_404(self):
        attempt = self.start().attempt
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("exam:play", args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("exam:finish", args=[attempt.pk])).status_code, 404)

    def test_play_post_redirect_get(self):
        attempt = self.start().attempt
        ans = attempt.answers.get(order=1)
        url = reverse("exam:play", args=[attempt.pk])
        response = self.client.post(url, {"order": 1, "option": ans.payload["correct"], "t": 1500})
        self.assertRedirects(response, url + "?da=1")
        ans.refresh_from_db()
        self.assertEqual(ans.time_ms, 1500)
        self.assertContains(self.client.get(url + "?da=1"), 'id="exam-play"')

    def test_partial_header_renders_feedback_directly(self):
        attempt = self.start().attempt
        ans = attempt.answers.get(order=1)
        response = self.client.post(reverse("exam:play", args=[attempt.pk]),
                                    {"order": 1, "option": ans.payload["correct"]}, HTTP_X_EXAM_PARTIAL="1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "lb-fb is-ok")

    def test_full_run_to_result(self):
        attempt = self.start(count=4).attempt
        url = reverse("exam:play", args=[attempt.pk])
        for ans in attempt.answers.all():
            self.client.post(url, {"order": ans.order, "option": ans.payload["correct"]})
        self.assertRedirects(self.client.post(reverse("exam:finish", args=[attempt.pk])),
                             reverse("exam:result", args=[attempt.pk]))
        self.assertContains(self.client.get(reverse("exam:result", args=[attempt.pk])), "100%")
        self.assertRedirects(self.client.get(url), reverse("exam:result", args=[attempt.pk]))
        self.assertContains(self.client.get(reverse("exam:hub")), reverse("exam:result", args=[attempt.pk]))

    def test_unfinished_result_redirects_to_play(self):
        attempt = self.start().attempt
        self.assertRedirects(self.client.get(reverse("exam:result", args=[attempt.pk])),
                             reverse("exam:play", args=[attempt.pk]))

    def test_abandon(self):
        attempt = self.start().attempt
        self.client.post(reverse("exam:abandon", args=[attempt.pk]))
        self.assertFalse(ExamAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertFalse(ExamAnswer.objects.filter(attempt_id=attempt.pk).exists())
