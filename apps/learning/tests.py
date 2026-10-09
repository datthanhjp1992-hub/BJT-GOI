"""
Test cho SC03_TrangChu và các hàm thống kê ở apps.learning.services.

Chạy: python manage.py test apps.learning
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.vocabulary import selectors as vocab_selectors
from apps.vocabulary.models import Topic, Vocabulary, VocabularyTopic
from apps.gamification.models import Contribution
from apps.gamification.services import (
    CONTRIBUTION_TYPE_COMMENT,
    STATUS_APPROVED,
    STATUS_PENDING,
)

from . import services, srs
from .models import StudySession, UserVocabularyProgress

User = get_user_model()


class LearningTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="dat", password="MatKhauRatManh123", first_name="Đạt",
        )
        self.client.force_login(self.user)

    def _make_topic(self, name, slug, words, name_ja=""):
        topic = Topic.objects.create(name=name, slug=slug, name_ja=name_ja)
        for word in words:
            vocab = Vocabulary.objects.create(
                word=word, reading=word, meaning_vi="nghĩa " + word,
            )
            VocabularyTopic.objects.create(vocabulary=vocab, topic=topic)
        return topic

    def _progress(self, vocab, *, mastered=False, due_offset=None):
        return UserVocabularyProgress.objects.create(
            user=self.user,
            vocabulary=vocab,
            is_mastered=mastered,
            next_review_date=(
                None if due_offset is None
                else self.user.local_today() + timedelta(days=due_offset)
            ),
        )

    def _session(self, days_ago, topic=None):
        return StudySession.objects.create(
            user=self.user,
            topic=topic,
            session_type="flashcard",
            started_at=self.user.local_now() - timedelta(days=days_ago),
        )


class StreakTests(LearningTestCase):
    def test_no_session_means_zero(self):
        self.assertEqual(services.get_streak_days(self.user), 0)

    def test_consecutive_days_are_counted(self):
        for days_ago in (0, 1, 2):
            self._session(days_ago)
        self.assertEqual(services.get_streak_days(self.user), 3)

    def test_gap_breaks_the_streak(self):
        self._session(0)
        self._session(1)
        self._session(5)  # cách quãng -> không tính tiếp
        self.assertEqual(services.get_streak_days(self.user), 2)

    def test_streak_survives_a_day_not_yet_studied(self):
        """Chưa học hôm nay nhưng hôm qua có: ngày còn chưa hết, giữ chuỗi."""
        self._session(1)
        self._session(2)
        self.assertEqual(services.get_streak_days(self.user), 2)

    def test_streak_is_zero_after_two_empty_days(self):
        self._session(2)
        self._session(3)
        self.assertEqual(services.get_streak_days(self.user), 0)

    def test_multiple_sessions_same_day_count_once(self):
        self._session(0)
        self._session(0)
        self.assertEqual(services.get_streak_days(self.user), 1)


class StatsTests(LearningTestCase):
    def test_counts_mastered_and_due(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計", "меню"])
        words = list(topic.vocabularies.order_by("pk"))
        self._progress(words[0], mastered=True, due_offset=7)
        self._progress(words[1], due_offset=0)     # đến hạn hôm nay
        self._progress(words[2], due_offset=-3)    # quá hạn
        self._progress(words[3], due_offset=1)     # mai mới tới

        stats = services.get_learning_stats(self.user)
        self.assertEqual(stats["words_started"], 4)
        self.assertEqual(stats["words_mastered"], 1)
        self.assertEqual(stats["due_today"], 2)


class TopicInProgressTests(LearningTestCase):
    def test_none_when_user_has_not_started(self):
        self.assertIsNone(services.get_topic_in_progress(self.user))

    def test_uses_topic_of_latest_session(self):
        older = self._make_topic("Gia đình", "gia-dinh", ["家族", "父"])
        newer = self._make_topic("Công việc", "cong-viec", ["会議", "報告", "残業"])
        self._session(3, topic=older)
        self._session(0, topic=newer)

        result = services.get_topic_in_progress(self.user)
        self.assertEqual(result["topic"], newer)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["learned"], 0)
        self.assertEqual(result["percent"], 0)

    def test_falls_back_to_topic_with_most_progress(self):
        topic = self._make_topic("Du lịch", "du-lich", ["旅行", "空港"])
        for vocab in topic.vocabularies.all():
            self._progress(vocab)

        result = services.get_topic_in_progress(self.user)
        self.assertEqual(result["topic"], topic)
        self.assertEqual(result["learned"], 2)
        self.assertEqual(result["percent"], 100)


class SuggestedTopicTests(LearningTestCase):
    def test_prefers_untouched_topics(self):
        started = self._make_topic("Gia đình", "gia-dinh", ["家族"])
        self._progress(started.vocabularies.first())
        self._make_topic("Công việc", "cong-viec", ["会議", "報告"])
        self._make_topic("Du lịch", "du-lich", ["旅行"])

        suggested = services.get_suggested_topics(self.user, limit=2)
        self.assertEqual([t.slug for t in suggested], ["cong-viec", "du-lich"])
        self.assertEqual(suggested[0].word_count, 2)

    def test_ignores_topics_without_words(self):
        Topic.objects.create(name="Rỗng", slug="rong")
        self._make_topic("Công việc", "cong-viec", ["会議"])
        self.assertEqual(
            [t.slug for t in services.get_suggested_topics(self.user)], ["cong-viec"]
        )


class DashboardViewTests(LearningTestCase):
    def test_requires_login(self):
        self.client.logout()
        url = reverse("learning:dashboard")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_renders_stats_and_suggestions(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self._progress(topic.vocabularies.first(), mastered=True, due_offset=-1)
        self._session(0, topic=topic)

        response = self.client.get(reverse("learning:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "learning/dashboard.html")
        self.assertEqual(response.context["stats"]["words_mastered"], 1)
        self.assertEqual(response.context["stats"]["due_today"], 1)
        self.assertEqual(response.context["stats"]["streak_days"], 1)
        # spec.md T3.1 (c): một nút chính "Học hôm nay", không còn "Học tiếp chủ đề X".
        self.assertContains(response, reverse("learning:daily_start"))
        self.assertNotContains(response, reverse("learning:flashcard", args=[topic.slug]))
        self.assertNotIn("in_progress", response.context)

    def test_renders_for_brand_new_user(self):
        """Chưa có dữ liệu gì thì trang chủ vẫn phải ra 200, không 500."""
        response = self.client.get(reverse("learning:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["daily"]["total"], 0)
        self.assertContains(response, "Hôm nay xong rồi")


class FlashcardQueueTests(LearningTestCase):
    """apps.learning.services.get_flashcard_queue — nguồn hàng đợi của SC04."""

    def test_words_without_progress_are_new(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        queue = services.get_flashcard_queue(self.user, topic)
        self.assertEqual(len(queue), 2)

    def test_overdue_words_come_before_new_words(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計"])
        words = list(topic.vocabularies.order_by("pk"))
        self._progress(words[0], due_offset=-1)  # quá hạn -> xếp đầu
        # words[1], words[2] chưa có progress -> "mới", xếp sau

        queue = services.get_flashcard_queue(self.user, topic)
        self.assertEqual(queue[0], words[0])
        self.assertEqual(set(queue[1:]), {words[1], words[2]})

    def test_not_yet_due_words_are_excluded(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self._progress(vocab, due_offset=3)
        self.assertEqual(services.get_flashcard_queue(self.user, topic), [])

    def test_reviewing_removes_the_word_from_the_queue(self):
        """review_word() luôn đẩy next_review_date sang ít nhất NGÀY MAI, nên
        thẻ vừa ôn phải tự rời hàng đợi ở lần gọi kế tiếp — không cần lọc tay
        thẻ "vừa ôn xong trong phiên này" ở get_flashcard_queue()."""
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        progress = UserVocabularyProgress.objects.create(user=self.user, vocabulary=vocab)
        services.review_word(progress, 5)
        self.assertEqual(services.get_flashcard_queue(self.user, topic), [])


class FlashcardViewTests(LearningTestCase):
    def test_requires_login(self):
        self.client.logout()
        url = reverse("learning:flashcard", args=["nha-hang"])
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_404_for_unknown_topic(self):
        response = self.client.get(reverse("learning:flashcard", args=["khong-ton-tai"]))
        self.assertEqual(response.status_code, 404)

    def test_session_complete_state_when_nothing_is_due(self):
        self._make_topic("Rỗng", "rong", [])
        response = self.client.get(reverse("learning:flashcard", args=["rong"]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["word"])

    def test_shows_first_word_with_progress_counters(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        response = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 2)
        self.assertEqual(response.context["position"], 1)
        self.assertContains(response, response.context["word"].word)

    def test_forgotten_word_does_not_grow_the_total(self):
        """Bấm Quên thì từ quay lại sau vài phút — "Thẻ x/N" vẫn đếm theo TỪ,
        mẫu số không được tăng thêm (trước đây 1/2 -> 2/3)."""
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        url = reverse("learning:flashcard", args=["nha-hang"])
        first = self.client.get(url).context["word"]
        self.client.post(
            reverse("learning:flashcard_review", args=[first.pk]),
            {"quality": "quen", "topic_slug": "nha-hang"},
        )
        page = self.client.get(url)
        self.assertEqual(page.context["total"], 2)
        self.assertEqual(page.context["position"], 1)

    def test_first_visit_creates_a_study_session(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        self.assertEqual(
            StudySession.objects.filter(user=self.user, session_type="flashcard").count(), 1
        )

    def test_reloading_the_page_reuses_the_same_session(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        self.assertEqual(StudySession.objects.count(), 1)


class FlashcardReviewTests(LearningTestCase):
    def test_get_is_not_allowed(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        response = self.client.get(reverse("learning:flashcard_review", args=[vocab.pk]))
        self.assertEqual(response.status_code, 405)

    def test_review_advances_next_review_date_and_redirects(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))  # mở phiên

        url = reverse("learning:flashcard_review", args=[vocab.pk])
        response = self.client.post(url, {"quality": "de", "topic_slug": "nha-hang"})

        self.assertRedirects(response, reverse("learning:flashcard", args=["nha-hang"]))
        progress = UserVocabularyProgress.objects.get(user=self.user, vocabulary=vocab)
        self.assertGreater(progress.next_review_date, self.user.local_today())

    def test_review_updates_the_open_study_session_counts(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        url = reverse("learning:flashcard_review", args=[vocab.pk])
        self.client.post(url, {"quality": "de", "topic_slug": "nha-hang"})

        session = StudySession.objects.get(user=self.user, topic=topic)
        self.assertEqual(session.words_reviewed, 1)
        self.assertEqual(session.correct_answers, 1)

    def test_forgot_is_not_counted_as_correct(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        url = reverse("learning:flashcard_review", args=[vocab.pk])
        self.client.post(url, {"quality": "quen", "topic_slug": "nha-hang"})

        session = StudySession.objects.get(user=self.user, topic=topic)
        self.assertEqual(session.words_reviewed, 1)
        self.assertEqual(session.correct_answers, 0)

    def test_finishing_the_queue_closes_the_study_session(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        url = reverse("learning:flashcard_review", args=[vocab.pk])
        self.client.post(url, {"quality": "de", "topic_slug": "nha-hang"})
        # Hàng đợi rỗng -> lần GET tiếp theo phải đóng phiên (ended_at có giá trị).
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))

        session = StudySession.objects.get(user=self.user, topic=topic)
        self.assertIsNotNone(session.ended_at)


class FlashcardCommentTests(LearningTestCase):
    def test_submitting_publishes_the_comment_immediately(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        url = reverse("learning:flashcard_comment", args=[vocab.pk])

        self.client.post(url, {"comment_text": "Ghi chú test", "topic_slug": "nha-hang"})

        contribution = Contribution.objects.get(target_vocabulary=vocab)
        self.assertEqual(contribution.contribution_type_code, CONTRIBUTION_TYPE_COMMENT)
        self.assertEqual(contribution.status_code, STATUS_APPROVED)
        self.assertEqual(contribution.comment_text, "Ghi chú test")
        self.assertEqual(contribution.user, self.user)

    def test_blank_comment_is_not_saved(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        url = reverse("learning:flashcard_comment", args=[vocab.pk])

        self.client.post(url, {"comment_text": "   ", "topic_slug": "nha-hang"})

        self.assertFalse(Contribution.objects.exists())

    def test_only_approved_comments_show_on_the_flashcard_page(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        Contribution.objects.create(
            user=self.user, contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            target_vocabulary=vocab, comment_text="Chờ duyệt", status_code=STATUS_PENDING,
        )
        Contribution.objects.create(
            user=self.user, contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            target_vocabulary=vocab, comment_text="Đã duyệt", status_code=STATUS_APPROVED,
        )

        response = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))

        self.assertContains(response, "Đã duyệt")
        self.assertNotContains(response, "Chờ duyệt")

    def test_new_comment_shows_on_the_card_right_away_with_delete_button(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.post(
            reverse("learning:flashcard_comment", args=[vocab.pk]),
            {"comment_text": "Hiện ngay", "topic_slug": "nha-hang"},
        )
        c = Contribution.objects.get(target_vocabulary=vocab)

        response = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))

        self.assertContains(response, "Hiện ngay")
        self.assertContains(response, reverse("gamification:comment_delete", args=[c.pk]))


class QuizChoicesTests(LearningTestCase):
    """apps.learning.services.get_quiz_choices — nguồn 4 lựa chọn của SC06."""

    def test_returns_correct_word_plus_distractors_from_same_topic(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計", "メニュー"])
        word = topic.vocabularies.first()

        choices = services.get_quiz_choices(word, topic)

        self.assertEqual(len(choices), 4)
        self.assertIn(word, choices)
        self.assertEqual(len({c.pk for c in choices}), 4)  # không trùng đáp án

    def test_fills_up_from_other_topics_when_topic_is_too_small(self):
        topic = self._make_topic("Nhỏ", "nho", ["注文", "予約"])
        self._make_topic("Khác", "khac", ["会計", "メニュー", "領収書"])
        word = topic.vocabularies.first()

        choices = services.get_quiz_choices(word, topic)

        self.assertEqual(len(choices), 4)
        self.assertIn(word, choices)

    def test_returns_fewer_choices_when_the_whole_dictionary_is_too_small(self):
        """Chỉ có 2 từ trong TOÀN BỘ từ điển -> không đủ 4 lựa chọn, trả về ít
        hơn thay vì ném lỗi giữa lúc người học đang làm bài."""
        topic = self._make_topic("Nhỏ", "nho", ["注文", "予約"])
        word = topic.vocabularies.first()

        choices = services.get_quiz_choices(word, topic)

        self.assertEqual(len(choices), 2)
        self.assertIn(word, choices)


class QuizViewTests(LearningTestCase):
    def test_requires_login(self):
        self.client.logout()
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        url = reverse("learning:quiz", args=["nha-hang"])
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_404_for_unknown_topic(self):
        response = self.client.get(reverse("learning:quiz", args=["khong-ton-tai"]))
        self.assertEqual(response.status_code, 404)

    def test_session_complete_state_when_nothing_is_due(self):
        self._make_topic("Rỗng", "rong", [])
        response = self.client.get(reverse("learning:quiz", args=["rong"]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["word"])

    def test_shows_first_question_with_four_choices(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計", "メニュー"])
        response = self.client.get(reverse("learning:quiz", args=["nha-hang"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 4)
        self.assertEqual(response.context["position"], 1)
        self.assertEqual(len(response.context["choices"]), 4)

    def test_first_visit_creates_a_quiz_study_session(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self.client.get(reverse("learning:quiz", args=["nha-hang"]))
        self.assertEqual(
            StudySession.objects.filter(user=self.user, session_type="quiz").count(), 1
        )

    def test_flashcard_and_quiz_sessions_of_the_same_topic_do_not_collide(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        self.client.get(reverse("learning:quiz", args=["nha-hang"]))
        self.assertEqual(
            StudySession.objects.filter(user=self.user, session_type="flashcard").count(), 1
        )
        self.assertEqual(
            StudySession.objects.filter(user=self.user, session_type="quiz").count(), 1
        )


class QuizAnswerTests(LearningTestCase):
    def test_get_is_not_allowed(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        url = reverse("learning:quiz_answer", args=["nha-hang", vocab.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_correct_answer_on_a_new_word_goes_through_the_learning_steps(self):
        """Từ mới trả lời đúng lần đầu -> bước học 10 phút (vẫn trong lượt);
        đúng thêm lần nữa mới tốt nghiệp sang lịch theo ngày."""
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:quiz", args=["nha-hang"]))  # mở phiên
        url = reverse("learning:quiz_answer", args=["nha-hang", vocab.pk])

        response = self.client.post(url, {"choice": str(vocab.pk)})

        self.assertRedirects(response, reverse("learning:quiz", args=["nha-hang"]))
        progress = UserVocabularyProgress.objects.get(user=self.user, vocabulary=vocab)
        self.assertEqual(progress.card_state, "learning")
        self.assertEqual(progress.next_review_date, self.user.local_today())
        self.assertIsNotNone(progress.due_at)

        self.client.post(url, {"choice": str(vocab.pk)})
        progress.refresh_from_db()
        self.assertEqual(progress.card_state, "review")
        self.assertGreater(progress.next_review_date, self.user.local_today())

    def test_wrong_answer_resets_srs_level_and_counts_as_wrong(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:quiz", args=["nha-hang"]))
        url = reverse("learning:quiz_answer", args=["nha-hang", vocab.pk])

        self.client.post(url, {"choice": "999999"})  # id không khớp -> sai

        progress = UserVocabularyProgress.objects.get(user=self.user, vocabulary=vocab)
        self.assertEqual(progress.srs_level, 0)
        self.assertEqual(progress.wrong_count, 1)

    def test_updates_the_open_quiz_session_counts(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:quiz", args=["nha-hang"]))
        url = reverse("learning:quiz_answer", args=["nha-hang", vocab.pk])

        self.client.post(url, {"choice": str(vocab.pk)})

        session = StudySession.objects.get(user=self.user, topic=topic, session_type="quiz")
        self.assertEqual(session.words_reviewed, 1)
        self.assertEqual(session.correct_answers, 1)

    def test_finishing_the_queue_closes_the_session_and_flashes_the_score(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:quiz", args=["nha-hang"]))
        url = reverse("learning:quiz_answer", args=["nha-hang", vocab.pk])
        # Từ mới phải đúng 2 lần (qua hết bước học) mới rời lượt kiểm tra.
        self.client.post(url, {"choice": str(vocab.pk)})
        self.client.post(url, {"choice": str(vocab.pk)})

        response = self.client.get(reverse("learning:quiz", args=["nha-hang"]))

        session = StudySession.objects.get(user=self.user, topic=topic, session_type="quiz")
        self.assertIsNotNone(session.ended_at)
        # Điểm đếm theo TỪ (1 từ, đúng ngay lần đầu), không theo lượt (2 lượt).
        self.assertContains(response, "1/1")


class StudySessionViewTests(LearningTestCase):
    """Phiên học theo BỘ LỌC của SC05 (nút "Bắt đầu học")."""

    def _start(self, **data):
        return self.client.post(reverse("learning:study_start"), data)

    def test_requires_login(self):
        self.client.logout()
        url = reverse("learning:study")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_start_is_post_only(self):
        self.assertEqual(self.client.get(reverse("learning:study_start")).status_code, 405)

    def test_queue_merges_every_selected_topic(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self._make_topic("Họp hành", "hop-hanh", ["議事録"])
        self._make_topic("Gia đình", "gia-dinh", ["家族"])

        response = self._start(topic=["nha-hang", "hop-hanh"], limit="0")
        self.assertRedirects(response, reverse("learning:study"))

        page = self.client.get(reverse("learning:study"))
        self.assertEqual(page.context["total"], 3)
        self.assertEqual(len(self.client.session["study_queue"]), 3)

    def test_no_topic_selected_means_every_word(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self._make_topic("Họp hành", "hop-hanh", ["議事録"])

        self._start(limit="0")
        self.assertEqual(len(self.client.session["study_queue"]), 2)

    def test_session_limit_caps_the_queue(self):
        self._make_topic("Nhà hàng", "nha-hang", ["語1", "語2", "語3", "語4"])

        self._start(topic="nha-hang", limit="10")
        self.assertEqual(len(self.client.session["study_queue"]), 4)

        self._start(topic="nha-hang", limit="20")
        self.assertEqual(len(self.client.session["study_queue"]), 4)

        self.client.post(reverse("learning:study_start"), {"topic": "nha-hang", "limit": "10"})
        queue = self.client.session["study_queue"]
        self.assertLessEqual(len(queue), 10)

    def test_missing_limit_means_every_word(self):
        """01/10/2026: SC05 mặc định "Tất cả" — POST thiếu/lạ limit thì học hết.

        Hạn mức từ mới (T6.1) nâng lên 30 để test chỉ đo `limit`."""
        self.user.daily_review_goal = 30
        self.user.save(update_fields=["daily_review_goal"])
        words = [f"語{i:02d}" for i in range(25)]
        self._make_topic("Nhiều từ", "nhieu-tu", words)
        self._start(topic="nhieu-tu")
        self.assertEqual(len(self.client.session["study_queue"]), 25)
        self._start(topic="nhieu-tu", limit="rac")
        self.assertEqual(len(self.client.session["study_queue"]), 25)

    def test_due_words_come_before_new_ones(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        due = topic.vocabularies.get(word="予約")
        self._progress(due, due_offset=-3)

        self._start(topic="nha-hang", limit="0")
        self.assertEqual(self.client.session["study_queue"][0], due.pk)

    def test_status_filter_is_honoured(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        learned = topic.vocabularies.get(word="予約")
        self._progress(learned, due_offset=1)

        self._start(topic="nha-hang", status="new", limit="0")
        queue = self.client.session["study_queue"]
        self.assertEqual(queue, [topic.vocabularies.get(word="注文").pk])

    def test_empty_result_flashes_and_goes_back(self):
        self._make_topic("Rỗng", "rong", [])
        response = self._start(topic="rong")
        self.assertRedirects(response, reverse("vocabulary:index"))
        self.assertFalse(self.client.session.get("study_queue"))

    def test_start_creates_a_study_session(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self._make_topic("Họp hành", "hop-hanh", ["議事録"])

        self._start(topic="nha-hang")
        session = StudySession.objects.get(user=self.user)
        self.assertEqual(session.topic.slug, "nha-hang")

        # Nhiều chủ đề -> không gán chủ đề nào cho phiên.
        self._start(topic=["nha-hang", "hop-hanh"])
        latest = StudySession.objects.order_by("-pk").first()
        self.assertIsNone(latest.topic)

    def test_reviewing_advances_the_queue_and_counts(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self._start(topic="nha-hang", limit="0")
        first_id = self.client.session["study_queue"][0]

        response = self.client.post(
            reverse("learning:study_review", args=[first_id]), {"quality": "nho"}
        )
        self.assertRedirects(response, reverse("learning:study"))
        self.assertNotIn(first_id, self.client.session["study_queue"])

        session = StudySession.objects.get(user=self.user, topic=topic)
        self.assertEqual(session.words_reviewed, 1)
        self.assertEqual(session.correct_answers, 1)
        self.assertTrue(
            UserVocabularyProgress.objects.filter(
                user=self.user, vocabulary_id=first_id
            ).exists()
        )

    def test_position_counter_walks_forward(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self._start(topic="nha-hang", limit="0")

        self.assertEqual(self.client.get(reverse("learning:study")).context["position"], 1)
        first_id = self.client.session["study_queue"][0]
        self.client.post(reverse("learning:study_review", args=[first_id]), {"quality": "de"})

        page = self.client.get(reverse("learning:study"))
        self.assertEqual(page.context["position"], 2)
        self.assertEqual(page.context["total"], 2)

    def test_forgotten_word_does_not_grow_the_total(self):
        """Quên/Khó đưa từ vào bước học chứ chưa rời phiên — tổng giữ nguyên
        bằng số từ lúc bắt đầu, tử số chỉ tăng khi từ rời phiên."""
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self._start(topic="nha-hang", limit="0")
        first_id = self.client.session["study_queue"][0]
        self.client.post(reverse("learning:study_review", args=[first_id]), {"quality": "quen"})

        page = self.client.get(reverse("learning:study"))
        self.assertEqual(page.context["total"], 2)
        self.assertEqual(page.context["position"], 1)

    def test_finishing_the_queue_closes_the_session(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self._start(topic="nha-hang", limit="0")
        vocab_id = self.client.session["study_queue"][0]
        self.client.post(reverse("learning:study_review", args=[vocab_id]), {"quality": "de"})

        response = self.client.get(reverse("learning:study"))
        self.assertIsNone(response.context["word"])
        self.assertIsNotNone(StudySession.objects.get(user=self.user, topic=topic).ended_at)
        self.assertIsNone(self.client.session.get("study_queue"))

    def test_end_button_closes_the_session_early(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self._start(topic="nha-hang", limit="0")

        response = self.client.post(reverse("learning:study_end"))
        self.assertRedirects(response, reverse("learning:dashboard"))
        self.assertIsNone(self.client.session.get("study_queue"))
        self.assertIsNotNone(StudySession.objects.get(user=self.user, topic=topic).ended_at)

    def test_report_and_suggest_links_live_on_the_study_page(self):
        """Góp ý + báo lỗi đã chuyển từ bảng SC05 sang màn học chi tiết."""
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self._start(topic="nha-hang", limit="0")

        response = self.client.get(reverse("learning:study"))
        word = response.context["word"]
        self.assertContains(response, reverse("error_reports:create") + "?vocabulary=%s" % word.pk)
        self.assertContains(response, reverse("gamification:form") + "?type=meaning&vocabulary=%s" % word.pk)

    def test_deleted_word_is_skipped_not_crashed(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self._start(topic="nha-hang", limit="0")
        gone_id = self.client.session["study_queue"][0]
        Vocabulary.objects.filter(pk=gone_id).delete()

        response = self.client.get(reverse("learning:study"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["word"])
        self.assertNotEqual(response.context["word"].pk, gone_id)


# =============================================================================
# SC15 — Ôn tập
# =============================================================================


class ReviewTestCase(LearningTestCase):
    """Tiện ích dựng tiến độ học với đủ các tham số SC15 quan tâm."""

    def _learned(self, vocab, *, due_offset=None, mastered=False,
                 srs_level=0, correct=0, wrong=0):
        return UserVocabularyProgress.objects.create(
            user=self.user,
            vocabulary=vocab,
            is_mastered=mastered,
            srs_level=srs_level,
            correct_count=correct,
            wrong_count=wrong,
            next_review_date=(
                None if due_offset is None
                else self.user.local_today() + timedelta(days=due_offset)
            ),
        )


class StudiedVocabularySelectorTests(ReviewTestCase):
    """`selectors.studied_vocabulary()` — trái tim của SC15."""

    def setUp(self):
        super().setUp()
        self.topic = self._make_topic("Họp hành", "hop-hanh", ["会議", "議事録", "稟議", "決裁", "契約"])
        self.words = {v.word: v for v in Vocabulary.objects.all()}

    def test_never_returns_a_word_the_user_has_not_studied(self):
        """Khác hẳn SC05: từ chưa có tiến độ KHÔNG bao giờ lọt vào trang ôn tập."""
        self._learned(self.words["会議"], due_offset=0)
        result = vocab_selectors.studied_vocabulary(self.user, scope=vocab_selectors.SCOPE_DUE)
        self.assertEqual([v.word for v in result], ["会議"])

    def test_another_users_progress_does_not_count(self):
        other = User.objects.create_user(username="khac", password="MatKhauRatManh123")
        UserVocabularyProgress.objects.create(
            user=other, vocabulary=self.words["会議"], next_review_date=other.local_today(),
        )
        result = vocab_selectors.studied_vocabulary(self.user, scope=vocab_selectors.SCOPE_DUE)
        self.assertEqual(list(result), [])

    def test_due_scope_covers_overdue_today_and_unscheduled(self):
        self._learned(self.words["会議"], due_offset=-3)   # quá hạn
        self._learned(self.words["議事録"], due_offset=0)   # hôm nay
        self._learned(self.words["稟議"], due_offset=None)  # có tiến độ, chưa xếp lịch
        self._learned(self.words["決裁"], due_offset=5)     # chưa đến hạn

        result = vocab_selectors.studied_vocabulary(self.user, scope=vocab_selectors.SCOPE_DUE)
        self.assertEqual(sorted(v.word for v in result), sorted(["会議", "議事録", "稟議"]))

    def test_upcoming_scope_excludes_words_already_due(self):
        self._learned(self.words["会議"], due_offset=0)     # đến hạn -> KHÔNG phải "sắp"
        self._learned(self.words["議事録"], due_offset=3)    # trong 7 ngày
        self._learned(self.words["稟議"], due_offset=30)     # quá xa

        result = vocab_selectors.studied_vocabulary(self.user, scope=vocab_selectors.SCOPE_UPCOMING)
        self.assertEqual([v.word for v in result], ["議事録"])

    def test_leech_scope_needs_more_wrong_than_right_and_at_least_two(self):
        self._learned(self.words["会議"], correct=2, wrong=7)   # hay quên
        self._learned(self.words["議事録"], correct=0, wrong=1)  # sai đúng 1 lần -> chưa tính
        self._learned(self.words["稟議"], correct=5, wrong=3)    # đúng nhiều hơn sai

        result = vocab_selectors.studied_vocabulary(self.user, scope=vocab_selectors.SCOPE_LEECH)
        self.assertEqual([v.word for v in result], ["会議"])

    def test_topic_filter_applies_on_top_of_the_scope(self):
        other_topic = self._make_topic("Điện thoại", "dien-thoai", ["電話"])
        self._learned(self.words["会議"], due_offset=0)
        self._learned(Vocabulary.objects.get(word="電話"), due_offset=0)

        result = vocab_selectors.studied_vocabulary(
            self.user, topics=[other_topic], scope=vocab_selectors.SCOPE_DUE
        )
        self.assertEqual([v.word for v in result], ["電話"])

    def test_unknown_scope_falls_back_to_due_instead_of_crashing(self):
        self.assertEqual(vocab_selectors.clean_review_scope("linh-tinh"), vocab_selectors.SCOPE_DUE)

    def test_only_extra_scopes_skip_the_schedule(self):
        self.assertTrue(vocab_selectors.touches_schedule(vocab_selectors.SCOPE_DUE))
        # "Hay quên" là ôn thêm từ 26/09/2026 — từ hay quên đã đến hạn thì vẫn
        # được xếp lịch trong phạm vi "đến hạn".
        self.assertFalse(vocab_selectors.touches_schedule(vocab_selectors.SCOPE_LEECH))
        self.assertFalse(vocab_selectors.touches_schedule(vocab_selectors.SCOPE_UPCOMING))
        self.assertFalse(vocab_selectors.touches_schedule(vocab_selectors.SCOPE_MASTERED))


class ReviewStatsServiceTests(ReviewTestCase):

    def setUp(self):
        super().setUp()
        self.topic = self._make_topic("Họp hành", "hop-hanh", ["会議", "議事録", "稟議", "決裁"])
        self.words = {v.word: v for v in Vocabulary.objects.all()}

    def test_overview_counts_and_rounds_minutes_up(self):
        self._learned(self.words["会議"], due_offset=-2)
        self._learned(self.words["議事録"], due_offset=0)
        self._learned(self.words["稟議"], due_offset=4)
        self._learned(self.words["決裁"], due_offset=9, mastered=True, srs_level=6)

        overview = services.get_review_overview(self.user)
        self.assertEqual(overview["studied"], 4)
        self.assertEqual(overview["overdue"], 1)
        self.assertEqual(overview["due_today"], 1)
        self.assertEqual(overview["due_total"], 2)
        self.assertEqual(overview["upcoming"], 1)
        self.assertEqual(overview["mastered"], 1)
        # 2 từ x 20 giây = 40 giây -> "khoảng 1 phút", không phải 0.
        self.assertEqual(overview["minutes"], 1)
        self.assertEqual(overview["overdue_percent"] + overview["due_today_percent"], 100)

    def test_overview_of_a_brand_new_user_is_all_zero(self):
        overview = services.get_review_overview(self.user)
        self.assertEqual(overview["studied"], 0)
        self.assertEqual(overview["minutes"], 0)
        # Không được chia cho 0 khi chưa có từ nào đến hạn.
        self.assertEqual(overview["overdue_percent"], 0)

    def test_memory_bands_split_by_srs_level(self):
        self._learned(self.words["会議"], srs_level=0)
        self._learned(self.words["議事録"], srs_level=3)
        self._learned(self.words["稟議"], srs_level=5)
        self._learned(self.words["決裁"], srs_level=9)

        bands = {row["key"]: row for row in services.get_memory_distribution(self.user)}
        self.assertEqual(bands["fresh"]["count"], 1)
        self.assertEqual(bands["learning"]["count"], 1)
        self.assertEqual(bands["mastered"]["count"], 2)
        self.assertEqual(sum(row["count"] for row in bands.values()), 4)

    def test_calendar_puts_overdue_first_and_unscheduled_words_on_today(self):
        self._learned(self.words["会議"], due_offset=-5)
        self._learned(self.words["議事録"], due_offset=None)
        self._learned(self.words["稟議"], due_offset=2)

        buckets = services.get_review_calendar(self.user, days=7)
        self.assertEqual(len(buckets), 8)          # 1 cột quá hạn + 7 ngày
        self.assertTrue(buckets[0]["is_overdue"])
        self.assertEqual(buckets[0]["count"], 1)
        self.assertTrue(buckets[1]["is_today"])
        self.assertEqual(buckets[1]["count"], 1)   # từ chưa xếp lịch nằm ở hôm nay
        self.assertEqual(buckets[3]["count"], 1)
        self.assertEqual(max(b["percent"] for b in buckets), 100)

    def test_topic_rows_sort_the_most_overdue_topic_first(self):
        quiet = self._make_topic("Giao hàng", "giao-hang", ["納品"])
        self._learned(self.words["会議"], due_offset=0)
        self._learned(self.words["議事録"], due_offset=0)
        self._learned(Vocabulary.objects.get(word="納品"), due_offset=30)

        rows = services.get_topic_review_rows(self.user)
        self.assertEqual([row["topic"].slug for row in rows], ["hop-hanh", "giao-hang"])
        self.assertEqual(rows[0]["due"], 2)
        self.assertEqual(rows[0]["learned"], 2)
        self.assertEqual(rows[0]["total"], 4)
        self.assertEqual(rows[0]["percent"], 50)
        self.assertEqual(rows[1]["due"], 0)
        self.assertEqual(quiet.slug, rows[1]["topic"].slug)

    def test_topic_rows_skip_topics_the_user_never_touched(self):
        self._make_topic("Chưa học", "chua-hoc", ["未習"])
        self._learned(self.words["会議"], due_offset=0)
        rows = services.get_topic_review_rows(self.user)
        self.assertEqual([row["topic"].slug for row in rows], ["hop-hanh"])


class RecordExtraReviewTests(ReviewTestCase):
    """Ôn thêm ngoài lịch KHÔNG được đụng vào lịch SM-2."""

    def setUp(self):
        super().setUp()
        self._make_topic("Họp hành", "hop-hanh", ["会議"])
        self.word = Vocabulary.objects.get(word="会議")

    def test_extra_review_keeps_the_schedule_untouched(self):
        progress = self._learned(self.word, due_offset=12, srs_level=4, correct=4)
        before = (progress.next_review_date, progress.srs_level,
                  progress.interval_days, progress.ease_factor)

        services.record_extra_review(progress, 5)
        progress.refresh_from_db()

        self.assertEqual(progress.correct_count, 5)
        self.assertEqual(
            (progress.next_review_date, progress.srs_level,
             progress.interval_days, progress.ease_factor),
            before,
            msg="Ôn thêm không được đẩy lịch — xem services.record_extra_review",
        )

    def test_extra_review_counts_a_wrong_answer(self):
        progress = self._learned(self.word, due_offset=12, srs_level=4)
        services.record_extra_review(progress, 0)
        progress.refresh_from_db()
        self.assertEqual(progress.wrong_count, 1)
        self.assertEqual(progress.srs_level, 4)


class ReviewViewTests(ReviewTestCase):

    def setUp(self):
        super().setUp()
        self._make_topic("Họp hành", "hop-hanh", ["会議", "議事録"])
        self.words = {v.word: v for v in Vocabulary.objects.all()}

    def test_requires_login(self):
        self.client.logout()
        url = reverse("learning:review")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_brand_new_user_gets_the_empty_state_not_a_crash(self):
        response = self.client.get(reverse("learning:review"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["overview"]["studied"], 0)

    def test_shows_how_many_words_are_due(self):
        self._learned(self.words["会議"], due_offset=-1)
        self._learned(self.words["議事録"], due_offset=0)
        response = self.client.get(reverse("learning:review"))
        self.assertEqual(response.context["overview"]["due_total"], 2)

    def test_tabs_switch_the_panel_through_the_query_string(self):
        """Ba tab là ba góc nhìn đổi bằng ?view= — không cần JavaScript."""
        self._learned(self.words["会議"], due_offset=0)

        topic_view = self.client.get(reverse("learning:review"))
        self.assertEqual(topic_view.context["active_view"], "topic")
        self.assertTrue(topic_view.context["topic_rows"])
        self.assertFalse(topic_view.context["calendar"])

        calendar_view = self.client.get(reverse("learning:review") + "?view=calendar")
        self.assertEqual(calendar_view.context["active_view"], "calendar")
        self.assertTrue(calendar_view.context["calendar"])
        self.assertFalse(calendar_view.context["topic_rows"])

    def test_topic_table_is_paginated_10_rows_by_default(self):
        """01/10/2026: bảng theo chủ đề phân trang như SC05 (mặc định 10 dòng)."""
        for i in range(12):
            topic = self._make_topic(f"Chủ đề {i:02d}", f"chu-de-{i:02d}", [f"題{i:02d}"])
            self._learned(topic.vocabularies.first(), due_offset=0)

        page1 = self.client.get(reverse("learning:review"))
        self.assertEqual(len(page1.context["topic_rows"]), 10)
        pager = page1.context["topic_pager"]
        self.assertGreaterEqual(pager["paginator"].count, 12)
        self.assertIn("view=topic", pager["query"])
        self.assertIn("per_page=10", pager["query"])
        self.assertContains(page1, 'name="per_page"')

        page2 = self.client.get(reverse("learning:review"), {"page": 2})
        self.assertEqual(len(page2.context["topic_rows"]), pager["paginator"].count - 10)

        five = self.client.get(reverse("learning:review"), {"per_page": 5})
        self.assertEqual(len(five.context["topic_rows"]), 5)
        bad = self.client.get(reverse("learning:review"), {"per_page": 7})
        self.assertEqual(bad.context["topic_pager"]["per_page"], 10)

    def test_unknown_view_falls_back_to_the_topic_tab(self):
        response = self.client.get(reverse("learning:review") + "?view=linh-tinh")
        self.assertEqual(response.context["active_view"], "topic")


class ReviewStartTests(ReviewTestCase):

    def setUp(self):
        super().setUp()
        self._make_topic("Họp hành", "hop-hanh", ["会議", "議事録", "稟議"])
        self.words = {v.word: v for v in Vocabulary.objects.all()}

    def _start(self, **data):
        return self.client.post(reverse("learning:review_start"), data)

    def test_start_is_post_only(self):
        self.assertEqual(self.client.get(reverse("learning:review_start")).status_code, 405)

    def test_due_scope_builds_the_queue_and_marks_the_session_as_scheduled(self):
        self._learned(self.words["会議"], due_offset=-1)
        self._learned(self.words["議事録"], due_offset=0)
        self._learned(self.words["稟議"], due_offset=20)

        response = self._start(scope="due", limit="0")
        self.assertRedirects(response, reverse("learning:study"))
        self.assertEqual(len(self.client.session["study_queue"]), 2)
        self.assertTrue(self.client.session["study_touch_schedule"])

    def test_empty_group_says_so_instead_of_opening_an_empty_session(self):
        response = self._start(scope="leech")
        self.assertRedirects(response, reverse("learning:review"))
        self.assertNotIn("study_queue", self.client.session)

    def test_quiz_mode_goes_to_the_queue_based_quiz(self):
        self._learned(self.words["会議"], due_offset=0)
        response = self._start(scope="due", mode="quiz", limit="0")
        self.assertRedirects(response, reverse("learning:study_quiz"))

        page = self.client.get(reverse("learning:study_quiz"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["word"].word, "会議")
        self.assertTrue(page.context["choices"])

    def test_extra_review_session_does_not_move_the_schedule(self):
        """Ôn nhóm "sắp đến hạn" rồi trả lời -> lịch ôn giữ nguyên."""
        progress = self._learned(self.words["会議"], due_offset=5, srs_level=3)
        self._start(scope="upcoming", limit="0")
        self.assertFalse(self.client.session["study_touch_schedule"])

        self.client.post(
            reverse("learning:study_review", args=[self.words["会議"].pk]), {"quality": "de"},
        )
        progress.refresh_from_db()
        self.assertEqual(progress.next_review_date, self.user.local_today() + timedelta(days=5))
        self.assertEqual(progress.srs_level, 3)
        self.assertEqual(progress.correct_count, 1)

    def test_due_review_session_does_move_the_schedule(self):
        progress = self._learned(self.words["会議"], due_offset=0, srs_level=1)
        self._start(scope="due", limit="0")

        self.client.post(
            reverse("learning:study_review", args=[self.words["会議"].pk]), {"quality": "de"},
        )
        progress.refresh_from_db()
        self.assertGreater(progress.next_review_date, self.user.local_today())
        self.assertEqual(progress.srs_level, 2)

    def test_session_from_sc05_still_updates_the_schedule(self):
        """Luồng cũ (SC05) không có cờ nào -> mặc định vẫn là ôn chính thức."""
        progress = self._learned(self.words["会議"], due_offset=0, srs_level=1)
        self.client.post(reverse("learning:study_start"), {"topic": "hop-hanh", "limit": "0"})
        self.client.post(
            reverse("learning:study_review", args=[self.words["会議"].pk]), {"quality": "nho"},
        )
        progress.refresh_from_db()
        self.assertEqual(progress.srs_level, 2)

    def test_quiz_answer_counts_into_the_session(self):
        self._learned(self.words["会議"], due_offset=0)
        self._start(scope="due", mode="quiz", limit="0")
        self.client.post(
            reverse("learning:study_quiz_answer", args=[self.words["会議"].pk]),
            {"choice": str(self.words["会議"].pk)},
        )
        session = StudySession.objects.filter(user=self.user).latest("started_at")
        self.assertEqual(session.words_reviewed, 1)
        self.assertEqual(session.correct_answers, 1)


# =============================================================================
# Flow ôn tập kiểu Anki (26/09/2026): bước học, hạn mức từ mới, hoàn tác
# =============================================================================


class SrsScheduleTests(TestCase):
    """apps.learning.srs — hàm thuần, không chạm DB."""

    def test_new_word_forgot_comes_back_within_the_session(self):
        r = srs.schedule(srs.Card(), srs.AGAIN)
        self.assertTrue(r.in_session)
        self.assertEqual(r.card.state, srs.LEARNING)
        self.assertEqual(r.delay, timedelta(minutes=srs.LEARN_STEPS[0]))

    def test_new_word_graduates_after_every_step(self):
        r = srs.schedule(srs.Card(), srs.GOOD)
        self.assertTrue(r.in_session)
        r = srs.schedule(r.card, srs.GOOD)
        self.assertFalse(r.in_session)
        self.assertEqual(r.card.state, srs.REVIEW)
        self.assertEqual(r.card.interval_days, srs.GRADUATE_INTERVAL)
        self.assertEqual(r.card.repetitions, 1)

    def test_easy_on_a_new_word_graduates_at_once(self):
        r = srs.schedule(srs.Card(), srs.EASY)
        self.assertEqual(r.card.state, srs.REVIEW)
        self.assertEqual(r.card.interval_days, srs.EASY_INTERVAL)

    def test_hard_good_easy_always_give_different_delays(self):
        cards = [
            srs.Card(),
            srs.Card(state=srs.LEARNING, step=1),
            srs.Card(state=srs.REVIEW, interval_days=1, repetitions=1),
            srs.Card(state=srs.REVIEW, interval_days=6, repetitions=2),
            srs.Card(state=srs.REVIEW, interval_days=30, repetitions=5, ease=1.3),
        ]
        for card in cards:
            with self.subTest(card=card):
                hard, good, easy = (srs.schedule(card, q).delay for q in (srs.HARD, srs.GOOD, srs.EASY))
                self.assertLess(hard, good)
                self.assertLess(good, easy)

    def test_forgetting_a_review_word_relearns_it_and_lowers_ease(self):
        card = srs.Card(state=srs.REVIEW, interval_days=15, repetitions=3, ease=2.5)
        r = srs.schedule(card, srs.AGAIN)
        self.assertTrue(r.in_session)
        self.assertEqual(r.card.state, srs.RELEARNING)
        self.assertEqual(r.card.repetitions, 0)
        self.assertLess(r.card.ease, 2.5)
        back = srs.schedule(r.card, srs.GOOD)
        self.assertEqual(back.card.state, srs.REVIEW)
        self.assertEqual(back.card.interval_days, 1)

    def test_ease_never_drops_below_the_floor(self):
        card = srs.Card(state=srs.REVIEW, interval_days=3, repetitions=3, ease=srs.MIN_EASE)
        self.assertGreaterEqual(srs.schedule(card, srs.HARD).card.ease, srs.MIN_EASE)
        self.assertGreaterEqual(srs.schedule(card, srs.AGAIN).card.ease, srs.MIN_EASE)

    def test_unknown_quality_is_rejected(self):
        with self.assertRaises(ValueError):
            srs.schedule(srs.Card(), 2)


class TopicQueueTests(LearningTestCase):
    """services.get_topic_queue — hàng đợi SC04 theo flow mới."""

    def test_forgotten_word_stays_in_the_queue(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        progress = services.get_or_start_progress(self.user, vocab)
        services.review_word(progress, 0)

        queue = services.get_topic_queue(self.user, topic)
        self.assertEqual(queue.words, [vocab])
        self.assertEqual(queue.n_learning, 1)
        # Chưa tới giờ và không còn từ nào khác -> học trước, báo còn mấy phút.
        self.assertGreater(queue.ahead_minutes, 0)

    def test_learning_word_waits_until_the_round_is_done(self):
        """"Hết lượt rồi mới ôn lại": từ đang học dù đã tới giờ vẫn đứng sau
        từ đến hạn và từ mới."""
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計"])
        words = list(topic.vocabularies.order_by("pk"))
        self._progress(words[0], due_offset=-1)
        learning = services.get_or_start_progress(self.user, words[1])
        services.review_word(learning, 0, now=timezone.now() - timedelta(minutes=5))

        queue = services.get_topic_queue(self.user, topic)
        self.assertEqual(queue.words[:3], [words[0], words[2], words[1]])
        self.assertEqual((queue.n_learning, queue.n_review, queue.n_new), (1, 1, 1))
        self.assertEqual(queue.ahead_minutes, 0)

    def test_new_words_are_capped_by_the_daily_goal(self):
        self.user.daily_review_goal = 2
        self.user.save(update_fields=["daily_review_goal"])
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計", "献立"])

        queue = services.get_topic_queue(self.user, topic)
        self.assertEqual(queue.n_new, 2)
        self.assertFalse(queue.more_new)

        for vocab in queue.words:
            services.review_word(services.get_or_start_progress(self.user, vocab), 5)
        queue = services.get_topic_queue(self.user, topic)
        self.assertEqual(queue.words, [])
        self.assertEqual(queue.new_today, 2)
        self.assertTrue(queue.more_new)

    def test_unlocked_words_join_the_queue_past_the_daily_cap(self):
        self.user.daily_review_goal = 1
        self.user.save(update_fields=["daily_review_goal"])
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計"])
        first = services.get_topic_queue(self.user, topic).words[0]
        services.review_word(services.get_or_start_progress(self.user, first), 5)

        queue = services.get_topic_queue(self.user, topic)
        self.assertEqual(queue.words, [])
        self.assertEqual(queue.more_new_count, 2)

        extra = services.pick_extra_new_words(self.user, topic)
        self.assertEqual(len(extra), 1)  # tối đa = hạn mức mỗi ngày
        queue = services.get_topic_queue(self.user, topic, unlocked_ids=extra)
        self.assertEqual([w.pk for w in queue.words], extra)
        self.assertEqual(queue.more_new_count, 1)

    def test_daily_cap_counts_new_words_of_every_topic(self):
        self.user.daily_review_goal = 1
        self.user.save(update_fields=["daily_review_goal"])
        other = self._make_topic("Họp hành", "hop-hanh", ["議事録"])
        services.review_word(services.get_or_start_progress(self.user, other.vocabularies.first()), 5)

        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self.assertEqual(services.get_topic_queue(self.user, topic).n_new, 0)


class MoreNewWordsTests(LearningTestCase):
    """Nút "Học thêm N từ mới" khi đã chạm hạn mức (trang chủ + màn xong)."""

    def setUp(self):
        super().setUp()
        self.user.daily_review_goal = 1
        self.user.save(update_fields=["daily_review_goal"])
        self.topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計"])
        self.page = reverse("learning:flashcard", args=["nha-hang"])
        word = self.client.get(self.page).context["word"]
        self.client.post(
            reverse("learning:flashcard_review", args=[word.pk]),
            {"quality": "de", "topic_slug": "nha-hang"},
        )

    def test_done_screen_offers_more_new_words(self):
        page = self.client.get(self.page)
        self.assertIsNone(page.context["word"])
        self.assertTrue(page.context["queue"].more_new)
        self.assertContains(page, reverse("learning:flashcard_more_new", args=["nha-hang"]))

    def test_dashboard_says_done_when_the_daily_cap_is_used(self):
        """Hết hạn mức từ mới + không còn từ đến hạn -> "xong" và mời học thêm
        ở SC05 (khối "Học tiếp" cũ đã gỡ, spec.md T3.1 c)."""
        UserVocabularyProgress.objects.filter(user=self.user).update(
            card_state=srs.REVIEW, next_review_date=self.user.local_today() + timedelta(days=3),
        )
        page = self.client.get(reverse("learning:dashboard"))
        self.assertEqual(page.context["daily"]["new"], 0)
        self.assertEqual(page.context["daily"]["total"], 0)
        self.assertContains(page, reverse("vocabulary:index"))

    def test_more_new_unlocks_words_for_today(self):
        url = reverse("learning:flashcard_more_new", args=["nha-hang"])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), self.page)
        page = self.client.get(self.page)
        self.assertIsNotNone(page.context["word"])
        self.assertEqual(page.context["queue"].n_new, 1)


class FlashcardFlowTests(LearningTestCase):
    """SC04 với bước học, khoảng cách trên nút, hoàn tác và tổng kết."""

    def setUp(self):
        super().setUp()
        self.topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self.vocab = self.topic.vocabularies.first()
        self.page = reverse("learning:flashcard", args=["nha-hang"])
        self.review = reverse("learning:flashcard_review", args=[self.vocab.pk])

    def _grade(self, code):
        return self.client.post(self.review, {"quality": code, "topic_slug": "nha-hang"})

    def test_buttons_hide_the_interval_by_default(self):
        response = self.client.get(self.page)
        self.assertEqual([b["delay"] for b in response.context["grade_buttons"]], ["", "", "", ""])
        # Không HIỆN dưới nút. ("4 ngày" vẫn có trong data-toast — câu báo T6.4.)
        self.assertNotContains(response, "btn-grade-delay")

    def test_buttons_show_how_long_until_the_next_review(self):
        self.user.show_review_interval = True
        self.user.save(update_fields=["show_review_interval"])
        response = self.client.get(self.page)
        delays = [b["delay"] for b in response.context["grade_buttons"]]
        self.assertEqual(delays, ["1 phút", "6 phút", "10 phút", "4 ngày"])
        self.assertContains(response, "4 ngày")
        self.assertEqual(response.context["card_state"], "new")

    def test_forgotten_word_is_shown_again_in_the_same_session(self):
        self.client.get(self.page)
        self._grade("quen")

        response = self.client.get(self.page)
        self.assertEqual(response.context["word"], self.vocab)
        self.assertEqual(response.context["card_state"], "learning")
        self.assertGreater(response.context["ahead_minutes"], 0)
        # Cùng một phiên, không mở phiên mới.
        self.assertEqual(StudySession.objects.filter(user=self.user).count(), 1)

    def test_session_ends_only_after_the_word_graduates(self):
        self.client.get(self.page)
        self._grade("quen")
        self._grade("nho")
        self._grade("nho")

        response = self.client.get(self.page)
        self.assertIsNone(response.context["word"])
        summary = response.context["summary"]
        # 1 TỪ, lần đầu bấm Quên -> 0% nhớ ngay, 1 từ cần ôn thêm; 3 lượt chấm.
        self.assertEqual(
            (summary["words"], summary["percent"], summary["again"], summary["reviewed"]),
            (1, 0, 1, 3),
        )
        self.assertEqual(summary["again_words"], [self.vocab])
        self.assertContains(response, reverse("learning:study_retry"))
        self.assertIsNotNone(StudySession.objects.get(user=self.user).ended_at)

    def test_undo_a_new_word_forgets_it_completely(self):
        self.client.get(self.page)
        self._grade("de")
        self.assertTrue(UserVocabularyProgress.objects.filter(user=self.user).exists())

        response = self.client.post(reverse("learning:undo"))
        self.assertRedirects(response, self.page)
        self.assertFalse(UserVocabularyProgress.objects.filter(user=self.user).exists())
        self.assertEqual(services.count_new_words_today(self.user), 0)

        session = StudySession.objects.get(user=self.user)
        self.assertEqual(session.words_reviewed, 0)
        self.assertIsNone(session.ended_at)
        self.assertEqual(self.client.get(self.page).context["word"], self.vocab)

    def test_undo_after_the_last_card_reopens_the_session(self):
        self.client.get(self.page)
        self._grade("de")
        done = self.client.get(self.page)
        self.assertIsNone(done.context["word"])
        self.assertContains(done, "Hoàn tác")

        self.client.post(reverse("learning:undo"))
        response = self.client.get(self.page)
        self.assertEqual(response.context["word"], self.vocab)
        self.assertEqual(StudySession.objects.filter(user=self.user).count(), 1)

        self._grade("nho")
        session = StudySession.objects.get(user=self.user)
        self.assertEqual(session.words_reviewed, 1)

    def test_undo_restores_a_review_word_exactly(self):
        progress = self._progress(self.vocab, due_offset=0)
        progress.srs_level, progress.interval_days, progress.correct_count = 3, 12, 3
        progress.save()
        self.client.get(self.page)
        self._grade("quen")

        self.client.post(reverse("learning:undo"))
        progress.refresh_from_db()
        self.assertEqual(progress.card_state, "review")
        self.assertEqual((progress.srs_level, progress.interval_days), (3, 12))
        self.assertEqual((progress.correct_count, progress.wrong_count), (3, 0))
        self.assertEqual(progress.next_review_date, self.user.local_today())

    def test_nothing_to_undo_is_harmless(self):
        response = self.client.post(reverse("learning:undo"))
        self.assertRedirects(response, reverse("learning:dashboard"))

    def test_undo_is_post_only(self):
        self.assertEqual(self.client.get(reverse("learning:undo")).status_code, 405)

    def test_a_session_left_open_since_yesterday_is_replaced(self):
        self.client.get(self.page)
        old = StudySession.objects.get(user=self.user)
        StudySession.objects.filter(pk=old.pk).update(
            started_at=self.user.local_now() - timedelta(days=1)
        )

        self.client.get(self.page)
        old.refresh_from_db()
        self.assertIsNotNone(old.ended_at)
        self.assertEqual(StudySession.objects.filter(user=self.user).count(), 2)


class StudyFlowTests(ReviewTestCase):
    """Phiên theo hàng đợi (SC05/SC15) với bước học và hoàn tác."""

    def setUp(self):
        super().setUp()
        self._make_topic("Họp hành", "hop-hanh", ["会議", "議事録"])
        self.words = {v.word: v for v in Vocabulary.objects.all()}

    def _review(self, word, code):
        return self.client.post(
            reverse("learning:study_review", args=[self.words[word].pk]), {"quality": code}
        )

    def test_forgotten_word_comes_back_before_the_session_ends(self):
        self.client.post(reverse("learning:study_start"), {"topic": "hop-hanh", "limit": "0"})
        first = self.client.get(reverse("learning:study")).context["word"]
        self._review(first.word, "quen")
        self.assertIn(first.pk, self.client.session["study_learning"])

        second = self.client.get(reverse("learning:study")).context["word"]
        self.assertNotEqual(second, first)
        self._review(second.word, "de")

        # Hàng đợi hết nhưng từ vừa quên vẫn còn -> học trước, không kết thúc.
        again = self.client.get(reverse("learning:study"))
        self.assertEqual(again.context["word"], first)
        self.assertGreater(again.context["ahead_minutes"], 0)

        self._review(first.word, "nho")
        self._review(first.word, "nho")
        self.assertIsNone(self.client.get(reverse("learning:study")).context["word"])

    def test_leech_session_does_not_move_the_schedule(self):
        progress = self._learned(self.words["会議"], due_offset=4, srs_level=2, correct=1, wrong=3)
        self.client.post(reverse("learning:review_start"), {"scope": "leech", "limit": "0"})
        self.assertFalse(self.client.session["study_touch_schedule"])

        self._review("会議", "de")
        progress.refresh_from_db()
        self.assertEqual(progress.next_review_date, self.user.local_today() + timedelta(days=4))
        self.assertEqual(progress.srs_level, 2)

    def test_forgetting_in_an_extra_review_sends_the_word_to_the_back(self):
        self._learned(self.words["会議"], due_offset=3, srs_level=2)
        self._learned(self.words["議事録"], due_offset=3, srs_level=2)
        self.client.post(reverse("learning:review_start"), {"scope": "upcoming", "limit": "0"})
        first_id = self.client.session["study_queue"][0]

        self.client.post(reverse("learning:study_review", args=[first_id]), {"quality": "quen"})
        self.assertEqual(self.client.session["study_queue"][-1], first_id)
        self.assertEqual(len(self.client.session["study_queue"]), 2)

    def test_learning_word_comes_back_only_after_the_round(self):
        """Phương án A: từ bấm Quên đã tới giờ vẫn chờ hết hàng đợi."""
        self.client.post(reverse("learning:study_start"), {"topic": "hop-hanh", "limit": "0"})
        first = self.client.get(reverse("learning:study")).context["word"]
        self._review(first.word, "quen")
        UserVocabularyProgress.objects.filter(user=self.user, vocabulary=first).update(
            due_at=timezone.now() - timedelta(minutes=5)
        )

        second = self.client.get(reverse("learning:study"))
        self.assertNotEqual(second.context["word"], first)
        self.assertEqual((second.context["seen"], second.context["done"]), (1, 0))
        self._review(second.context["word"].word, "de")

        again = self.client.get(reverse("learning:study"))
        self.assertEqual(again.context["word"], first)
        self.assertTrue(again.context["is_repeat"])
        self.assertEqual((again.context["seen"], again.context["done"]), (2, 1))

    def test_summary_counts_words_not_gradings(self):
        self.client.post(reverse("learning:study_start"), {"topic": "hop-hanh", "limit": "0"})
        self._review("会議", "quen")
        self._review("議事録", "nho")
        for _ in range(2):
            self._review("会議", "nho")
        self._review("議事録", "nho")

        summary = self.client.get(reverse("learning:study")).context["summary"]
        self.assertEqual(
            (summary["words"], summary["remembered"], summary["again"], summary["reviewed"]),
            (2, 1, 1, 5),
        )
        self.assertEqual(summary["again_words"], [self.words["会議"]])

    def test_undo_of_the_first_grade_forgets_it(self):
        self.client.post(reverse("learning:study_start"), {"topic": "hop-hanh", "limit": "0"})
        first = self.client.get(reverse("learning:study")).context["word"]
        self._review(first.word, "quen")
        self.client.post(reverse("learning:undo"))

        page = self.client.get(reverse("learning:study"))
        self.assertEqual(page.context["word"], first)
        self.assertEqual(page.context["seen"], 0)
        self.assertFalse(page.context["is_repeat"])

    def test_retry_starts_an_extra_review_of_the_given_words(self):
        response = self.client.post(
            reverse("learning:study_retry"), {"vocab": [self.words["会議"].pk, "x"]}
        )
        self.assertRedirects(response, reverse("learning:study"))
        self.assertEqual(self.client.session["study_queue"], [self.words["会議"].pk])
        self.assertFalse(self.client.session["study_touch_schedule"])

        self._review("会議", "de")
        self.assertFalse(UserVocabularyProgress.objects.filter(
            user=self.user, vocabulary=self.words["会議"], card_state="review",
        ).exists())

    def test_retry_with_nothing_valid_goes_home(self):
        response = self.client.post(reverse("learning:study_retry"), {"vocab": ["0"]})
        self.assertRedirects(response, reverse("learning:dashboard"))

    def test_extra_review_hides_the_delay_previews(self):
        self.user.show_review_interval = True
        self.user.save(update_fields=["show_review_interval"])
        self._learned(self.words["会議"], due_offset=3, srs_level=2)
        self.client.post(reverse("learning:review_start"), {"scope": "upcoming", "limit": "0"})
        response = self.client.get(reverse("learning:study"))
        self.assertEqual([b["delay"] for b in response.context["grade_buttons"]], ["", "", "", ""])

    def test_undo_after_finishing_an_extra_review_keeps_it_extra(self):
        progress = self._learned(self.words["会議"], due_offset=3, srs_level=2)
        self.client.post(reverse("learning:review_start"), {"scope": "upcoming", "limit": "0"})
        self._review("会議", "de")
        self.assertIsNone(self.client.get(reverse("learning:study")).context["word"])

        response = self.client.post(reverse("learning:undo"))
        self.assertRedirects(response, reverse("learning:study"))
        self.assertFalse(self.client.session["study_touch_schedule"])
        page = self.client.get(reverse("learning:study"))
        self.assertEqual(page.context["word"], self.words["会議"])

        self._review("会議", "nho")
        progress.refresh_from_db()
        self.assertEqual(progress.next_review_date, self.user.local_today() + timedelta(days=3))
        self.assertEqual(progress.correct_count, 1)


class ReviewDeckFullSessionTests(ReviewTestCase):
    """Bug 27/09/2026: thẻ "Sắp đến hạn" ghi "Ôn 101 từ" nhưng lượt ôn chỉ có 20
    thẻ — form của thẻ gửi kèm limit=DEFAULT_SESSION_LIMIT. Các nút không có ô
    chọn số từ phải ôn ĐỦ con số đang hiện trên nút."""

    WORD_COUNT = 25  # > DEFAULT_SESSION_LIMIT (20)

    def setUp(self):
        super().setUp()
        words = [f"語{i:02d}" for i in range(self.WORD_COUNT)]
        self._make_topic("Nhiều từ", "nhieu-tu", words)
        for vocab in Vocabulary.objects.all():
            self._learned(vocab, due_offset=3)          # sắp đến hạn (trong 7 ngày)

    def _posted_limit(self, html, marker):
        """limit mà form chứa `marker` thật sự gửi đi — đọc từ HTML đã render."""
        import re
        for form in re.findall(r"<form[^>]*>.*?</form>", html, flags=re.S):
            if marker in form:
                return re.search(r'name="limit" value="([^"]*)"', form).group(1)
        self.fail(f"Không thấy form chứa {marker!r}")

    def test_deck_button_reviews_every_word_it_announces(self):
        page = self.client.get(reverse("learning:review"))
        deck = next(d for d in page.context["decks"] if d["scope"] == "upcoming")
        self.assertEqual(deck["count"], self.WORD_COUNT)

        limit = self._posted_limit(page.content.decode(), 'name="scope" value="upcoming"')
        self.client.post(reverse("learning:review_start"), {"scope": "upcoming", "limit": limit})
        self.assertEqual(len(self.client.session["study_queue"]), self.WORD_COUNT)
        self.assertEqual(self.client.session["study_total"], self.WORD_COUNT)

    def test_topic_row_button_reviews_every_due_word_of_the_topic(self):
        UserVocabularyProgress.objects.update(next_review_date=self.user.local_today())
        page = self.client.get(reverse("learning:review"))
        limit = self._posted_limit(page.content.decode(), 'type="hidden" name="topic" value="nhieu-tu"')
        self.client.post(reverse("learning:review_start"),
                         {"scope": "due", "topic": "nhieu-tu", "limit": limit})
        self.assertEqual(len(self.client.session["study_queue"]), self.WORD_COUNT)

    def test_due_card_still_honours_the_chosen_limit(self):
        """Khối "Đến hạn hôm nay" có <select> số từ -> vẫn cắt theo lựa chọn."""
        UserVocabularyProgress.objects.update(next_review_date=self.user.local_today())
        self.client.post(reverse("learning:review_start"), {"scope": "due", "limit": "10"})
        self.assertEqual(len(self.client.session["study_queue"]), 10)


# =============================================================================
# Phase 1 (02/10/2026, spec.md T1.1-T1.7) — màn học SC04
# =============================================================================

PARTIAL = {"HTTP_X_CARD_PARTIAL": "1"}


class CardPartialTests(LearningTestCase):
    """T1.1/T1.2 — cùng URL trả trang đầy đủ hoặc chỉ phần thẻ (fetch)."""

    def setUp(self):
        super().setUp()
        self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self.words = {v.word: v for v in Vocabulary.objects.all()}
        self.page = reverse("learning:flashcard", args=["nha-hang"])

    def _review_url(self, word):
        return reverse("learning:flashcard_review", args=[self.words[word].pk])

    def test_full_page_without_header(self):
        response = self.client.get(self.page)
        self.assertTemplateUsed(response, "learning/flashcard.html")
        self.assertTemplateUsed(response, "learning/_card_panel.html")
        self.assertContains(response, 'id="card-panel"')
        self.assertContains(response, "<html")
        self.assertNotIn("X-Card-Partial", response)
        # Hai dạng nội dung trên cùng URL -> phải khai Vary để không cache lẫn.
        self.assertIn("X-Card-Partial", response["Vary"])

    def test_header_returns_only_the_card(self):
        response = self.client.get(self.page, **PARTIAL)
        self.assertTemplateUsed(response, "learning/_card_panel.html")
        self.assertTemplateNotUsed(response, "learning/flashcard.html")
        self.assertTemplateNotUsed(response, "base.html")
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, 'id="card-panel"')
        self.assertEqual(response["X-Card-Partial"], "1")
        self.assertIn("X-Card-Partial", response["Vary"])
        self.assertContains(response, "data-study-card")

    def test_grading_follows_redirect_into_a_fragment(self):
        """JS gửi POST kèm header; view POST vẫn redirect như cũ, GET sau
        redirect phải trả fragment của thẻ KẾ TIẾP."""
        first = self.client.get(self.page).context["word"]
        response = self.client.post(
            self._review_url(first.word), {"quality": "de", "topic_slug": "nha-hang"},
            follow=True, **PARTIAL,
        )
        self.assertEqual(response["X-Card-Partial"], "1")
        self.assertNotContains(response, "<html")
        self.assertNotEqual(response.context["word"], first)
        self.assertTrue(
            UserVocabularyProgress.objects.filter(user=self.user, vocabulary=first).exists()
        )

    def test_grading_without_header_still_renders_the_full_page(self):
        first = self.client.get(self.page).context["word"]
        response = self.client.post(
            self._review_url(first.word), {"quality": "de", "topic_slug": "nha-hang"},
            follow=True,
        )
        self.assertTemplateUsed(response, "learning/flashcard.html")
        self.assertContains(response, "<html")

    def test_undo_fragment_carries_its_flash_message(self):
        """Fragment tự mang thông báo "Đã hoàn tác" (trang đầy đủ thì base.html in)."""
        first = self.client.get(self.page).context["word"]
        self.client.post(self._review_url(first.word), {"quality": "de", "topic_slug": "nha-hang"})
        response = self.client.post(reverse("learning:undo"), follow=True, **PARTIAL)
        self.assertEqual(response["X-Card-Partial"], "1")
        self.assertEqual(response.context["word"], first)
        self.assertContains(response, 'class="flash"')

    def test_full_page_does_not_print_flash_messages_twice(self):
        first = self.client.get(self.page).context["word"]
        self.client.post(self._review_url(first.word), {"quality": "de", "topic_slug": "nha-hang"})
        response = self.client.post(reverse("learning:undo"), follow=True)
        self.assertEqual(response.content.decode().count('class="flash"'), 1)

    def test_undo_with_nothing_left_is_not_a_fragment(self):
        """Hết gì để hoàn tác -> server đẩy về trang chủ (trang đầy đủ, không
        mang header) — JS dựa vào đó để chuyển hẳn trang thay vì nhét trang
        chủ vào khung thẻ."""
        response = self.client.post(reverse("learning:undo"), follow=True, **PARTIAL)
        self.assertTemplateUsed(response, "learning/dashboard.html")
        self.assertNotIn("X-Card-Partial", response)

    def test_finished_session_fragment_shows_the_summary(self):
        for word in ("予約", "注文"):
            self.client.get(self.page)
            self.client.post(self._review_url(word), {"quality": "de", "topic_slug": "nha-hang"})
        response = self.client.get(self.page, **PARTIAL)
        self.assertIsNone(response.context["word"])
        self.assertContains(response, "session-done")

    def test_study_view_supports_fragments_too(self):
        self.client.post(reverse("learning:study_start"), {"topic": "nha-hang", "limit": "0"})
        response = self.client.get(reverse("learning:study"), **PARTIAL)
        self.assertEqual(response["X-Card-Partial"], "1")
        self.assertTemplateNotUsed(response, "learning/flashcard.html")
        self.assertIsNotNone(response.context["word"])


class StudyScreenMarkupTests(LearningTestCase):
    """T1.3-T1.5 — móc data-* cho JS, hiện thẻ 2 bước, khu thảo luận gập."""

    def setUp(self):
        super().setUp()
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self.page = reverse("learning:flashcard", args=["nha-hang"])

    def test_grade_buttons_are_numbered_for_shortcuts(self):
        response = self.client.get(self.page)
        self.assertEqual([b["key"] for b in response.context["grade_buttons"]], [1, 2, 3, 4])
        # T2.2: màu nút đi qua class + token CSS, không còn style inline.
        self.assertEqual(
            [b["css"] for b in response.context["grade_buttons"]],
            ["is-forgot", "is-hard", "is-good", ""],
        )
        self.assertContains(response, "btn-grade is-forgot")
        for key in "1234":
            self.assertContains(response, f'data-grade-key="{key}"')
        self.assertContains(response, "data-shortcut-dialog")

    def test_card_hides_the_answer_behind_a_reveal_button(self):
        response = self.client.get(self.page)
        self.assertContains(response, "data-reveal")
        self.assertContains(response, 'class="after-reveal"')
        self.assertContains(response, "data-card-ajax")

    def test_reading_is_on_the_front_by_default(self):
        response = self.client.get(self.page)
        self.assertContains(response, 'class="reading"')
        self.assertNotContains(response, 'class="reading back-only"')

    def test_reading_moves_to_the_back_when_disabled(self):
        self.user.show_reading_on_front = False
        self.user.save(update_fields=["show_reading_on_front"])
        response = self.client.get(self.page)
        self.assertContains(response, 'class="reading back-only"')

    def test_page_turns_on_focus_mode(self):
        response = self.client.get(self.page)
        self.assertContains(response, "is-focus")
        self.assertContains(response, "data-sidebar-toggle")

    def test_other_pages_keep_the_sidebar(self):
        response = self.client.get(reverse("learning:dashboard"))
        self.assertNotContains(response, "is-focus")

    def test_discussion_shows_the_comment_count(self):
        vocab = Vocabulary.objects.get(word="注文")
        Contribution.objects.create(
            user=self.user, contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            status_code=STATUS_APPROVED, target_vocabulary=vocab, comment_text="Hay",
        )
        response = self.client.get(self.page)
        self.assertContains(response, "study-discussion")
        self.assertContains(response, "(1)")

    def test_posting_a_comment_returns_to_the_open_discussion(self):
        """Khu thảo luận mặc định gập — gửi xong phải quay về đúng neo để JS
        mở sẵn, người gửi thấy ngay bình luận của mình."""
        vocab = Vocabulary.objects.get(word="注文")
        response = self.client.post(
            reverse("learning:flashcard_comment", args=[vocab.pk]),
            {"comment_text": "Hay", "topic_slug": "nha-hang"},
        )
        self.assertRedirects(
            response, self.page + "#study-discussion", fetch_redirect_response=False
        )


class SessionSummaryTimeTests(LearningTestCase):
    """T1.7 — màn tổng kết có thời gian học (làm tròn lên) và streak."""

    def setUp(self):
        super().setUp()
        self.topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        self.vocab = self.topic.vocabularies.first()
        self.page = reverse("learning:flashcard", args=["nha-hang"])

    def test_summary_has_minutes_and_streak(self):
        self.client.get(self.page)
        self.client.post(
            reverse("learning:flashcard_review", args=[self.vocab.pk]),
            {"quality": "de", "topic_slug": "nha-hang"},
        )
        response = self.client.get(self.page)
        self.assertIsNone(response.context["word"])
        self.assertEqual(response.context["summary"]["minutes"], 1)
        self.assertEqual(response.context["streak_days"], 1)

    def test_minutes_round_up(self):
        from .views import _session_minutes

        now = timezone.now()
        session = StudySession(started_at=now - timedelta(seconds=61), ended_at=now)
        self.assertEqual(_session_minutes(session), 2)
        session.ended_at = session.started_at
        self.assertEqual(_session_minutes(session), 1)

    def test_retry_is_the_only_primary_action_when_words_were_forgotten(self):
        self.client.get(self.page)
        review = reverse("learning:flashcard_review", args=[self.vocab.pk])
        for code in ("quen", "nho", "nho"):
            self.client.post(review, {"quality": code, "topic_slug": "nha-hang"})
        html = self.client.get(self.page).content.decode()
        back = reverse("learning:dashboard")
        self.assertIn(f'class="btn btn-outline" href="{back}"', html)


class StudyScreenCssTests(TestCase):
    """Phase 1 thêm class mới cho màn học — cả 3 theme phải có (cùng tinh
    thần với accounts.tests ThemeCssTests cho SC08)."""

    REQUIRED_RULES = (
        ".js .study-screen:not(.is-revealed) .after-reveal",
        ".study-screen.is-revealed .before-reveal",
        ".app-shell.is-focus .site-sidebar",
        ".app-shell.is-focus.show-sidebar .site-sidebar",
        ".grade-row",
        ".kbd",
        ".shortcut-dialog",
        ".flashcard.swipe-left",
        ".flashcard.swipe-up",
        ".study-screen.is-revealed .flashcard{touch-action:none;}",
        ".session-done",
        "env(safe-area-inset-bottom)",
        "prefers-reduced-motion",
    )

    def test_learning_templates_have_no_fixed_inline_style(self):
        """spec.md T2.2 — style cố định đi qua class trong base.css; chỉ style
        phụ thuộc dữ liệu (có {{ }}, vd width:{{ percent }}%) được để inline."""
        import re
        from pathlib import Path

        from django.conf import settings

        folder = Path(settings.BASE_DIR) / "templates" / "learning"
        for path in folder.glob("*.html"):
            html = path.read_text(encoding="utf-8")
            for style in re.findall(r'style="([^"]*)"', html):
                with self.subTest(file=path.name, style=style):
                    self.assertIn("{{", style, msg=f"{path.name}: style cố định {style!r}")

    def test_mobile_rules_exist(self):
        """spec.md T2.4 — sidebar thành menu ☰ và bảng tự cuộn ngang ở màn hẹp."""
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "base.css").read_text(encoding="utf-8")
        for rule in (
            ".app-shell.show-sidebar .site-sidebar",
            "table:not([class]){display:block;max-width:100%;overflow-x:auto;",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, css)

    def test_every_theme_styles_the_study_screen(self):
        from pathlib import Path

        from django.conf import settings

        css_dir = Path(settings.BASE_DIR) / "static" / "css"
        shared = (css_dir / "base.css").read_text(encoding="utf-8")   # spec.md T2.1
        for name in ("theme_a.css", "theme_b.css", "theme_c.css"):
            css = (css_dir / name).read_text(encoding="utf-8") + shared
            for rule in self.REQUIRED_RULES:
                with self.subTest(file=name, rule=rule):
                    self.assertIn(rule, css, msg=f"{name} thiếu rule {rule} cho màn học")


# =============================================================================
# Phase 3 — luồng sử dụng (spec.md T3.1 – T3.4)
# =============================================================================


class DailyQueueTests(LearningTestCase):
    """T3.1 — hàng đợi "Học hôm nay" gom mọi chủ đề."""

    def _state(self, vocab, state, due_offset=0, due_at=None):
        progress = self._progress(vocab, due_offset=due_offset)
        progress.card_state = state
        progress.due_at = due_at
        progress.save()
        # Từ đã học từ hôm trước — không ăn vào hạn mức từ mới của hôm nay
        # (count_new_words_today đếm theo created_at).
        UserVocabularyProgress.objects.filter(pk=progress.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        return progress

    def _goal(self, value):
        self.user.daily_review_goal = value
        self.user.save(update_fields=["daily_review_goal"])

    def test_due_words_of_every_topic_oldest_first_then_learning(self):
        a = self._make_topic("A", "a", ["あ"]).vocabularies.get()
        b = self._make_topic("B", "b", ["い"]).vocabularies.get()
        c = self._make_topic("C", "c", ["う", "え"])
        c_learning, c_later = c.vocabularies.get(word="う"), c.vocabularies.get(word="え")
        self._state(a, srs.REVIEW, due_offset=0)
        self._state(b, srs.REVIEW, due_offset=-3)
        self._state(c_learning, srs.LEARNING, due_at=timezone.now())
        self._state(c_later, srs.REVIEW, due_offset=2)       # chưa tới hạn
        self._goal(0)

        self.assertEqual(services.build_daily_queue(self.user), [b.pk, a.pk, c_learning.pk])

    def test_new_words_come_from_the_topic_in_progress_then_suggestions(self):
        self._goal(3)
        current = self._make_topic("Đang học", "dang-hoc", ["か", "き", "く"])
        self._make_topic("Khác", "khac", ["さ", "し", "す", "せ"])
        self._state(current.vocabularies.get(word="か"), srs.REVIEW, due_offset=5)
        self._session(1, topic=current)

        queue = services.build_daily_queue(self.user)
        words = dict(Vocabulary.objects.filter(pk__in=queue).values_list("pk", "word"))
        # Hết 2 từ còn lại của chủ đề đang học mới sang chủ đề gợi ý.
        self.assertEqual([words[pk] for pk in queue], ["き", "く", "さ"])

    def test_new_words_never_exceed_the_daily_cap(self):
        self._goal(2)
        topic = self._make_topic("A", "a", ["あ", "い", "う", "え"])
        # Hôm nay đã học 1 từ mới -> còn 1.
        services.get_or_start_progress(self.user, topic.vocabularies.get(word="あ"))
        self.assertEqual(services.get_daily_overview(self.user)["new"], 1)

    def test_overview_counts_and_minutes(self):
        self._goal(2)
        topic = self._make_topic("A", "a", ["あ", "い", "う", "え"])
        self._state(topic.vocabularies.get(word="あ"), srs.REVIEW, due_offset=-1)
        overview = services.get_daily_overview(self.user)
        self.assertEqual((overview["due"], overview["new"], overview["total"]), (1, 2, 3))
        self.assertEqual(overview["minutes"], 1)   # 3 x 20 giây, làm tròn lên

    def test_done_state_reports_tomorrow(self):
        topic = self._make_topic("A", "a", ["あ"])
        self._state(topic.vocabularies.get(), srs.REVIEW, due_offset=1)
        overview = services.get_daily_overview(self.user)
        self.assertEqual(overview["total"], 0)
        self.assertEqual(overview["due_tomorrow"], 1)


class DailyStartViewTests(LearningTestCase):
    """T3.1 — nút "Học hôm nay" chạy bằng đúng luồng study_*."""

    def setUp(self):
        super().setUp()
        self.user.daily_review_goal = 1
        self.user.save(update_fields=["daily_review_goal"])
        self.topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self.url = reverse("learning:daily_start")

    def test_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_starts_a_study_session_with_the_daily_queue(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("learning:study"), fetch_redirect_response=False)
        self.assertIsNone(StudySession.objects.get(user=self.user).topic)
        self.assertEqual(self.client.session["study_total"], 1)
        self.assertTrue(self.client.session["study_touch_schedule"])
        page = self.client.get(reverse("learning:study"))
        expected = Vocabulary.objects.filter(topics=self.topic).order_by("word").first()
        self.assertEqual(page.context["word"], expected)

    def test_undoing_a_new_word_gives_the_cap_back(self):
        self.client.post(self.url)
        word = self.client.get(reverse("learning:study")).context["word"]
        self.client.post(reverse("learning:study_review", args=[word.pk]), {"quality": "de"})
        self.assertEqual(services.get_daily_overview(self.user)["new"], 0)

        self.client.post(reverse("learning:undo"))
        self.assertEqual(services.count_new_words_today(self.user), 0)
        self.assertEqual(services.get_daily_overview(self.user)["new"], 1)

    def test_nothing_left_goes_back_to_the_dashboard(self):
        self.user.daily_review_goal = 0
        self.user.save(update_fields=["daily_review_goal"])
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse("learning:dashboard"))
        self.assertContains(response, "Hôm nay bạn đã học xong")
        self.assertFalse(StudySession.objects.filter(user=self.user).exists())

    def test_review_start_still_keeps_its_flags_through_the_shared_helper(self):
        """review_start giờ đi qua _start_study_session — phiên "ôn thêm" phải
        giữ đúng cờ không đẩy lịch và chế độ trắc nghiệm."""
        self._progress(self.topic.vocabularies.get(word="注文"), due_offset=3)
        self.client.post(reverse("learning:review_start"), {
            "scope": vocab_selectors.SCOPE_UPCOMING, "mode": "quiz",
        })
        self.assertFalse(self.client.session["study_touch_schedule"])
        self.assertEqual(self.client.session["study_mode"], "quiz")
        self.assertEqual(self.client.session["study_learning"], [])


class OnboardingNudgeTests(LearningTestCase):
    """T3.2 — trang chủ mời mở lại hướng dẫn khi chưa học gì."""

    def test_brand_new_user_sees_the_nudge(self):
        response = self.client.get(reverse("learning:dashboard"))
        self.assertTrue(response.context["show_onboarding"])
        self.assertContains(response, reverse("accounts:onboarding"))

    def test_nudge_disappears_after_the_first_session(self):
        self._session(0)
        response = self.client.get(reverse("learning:dashboard"))
        self.assertFalse(response.context["show_onboarding"])
        self.assertNotContains(response, reverse("accounts:onboarding"))


class EmptyAndLoadingStateTests(LearningTestCase):
    """T3.3 — partial empty_state dùng chung + nút có data-loading-text."""

    def test_review_page_without_history_uses_the_shared_empty_state(self):
        response = self.client.get(reverse("learning:review"))
        self.assertTemplateUsed(response, "partials/empty_state.html")
        self.assertContains(response, "empty-state")

    def test_daily_button_has_a_loading_text(self):
        self._make_topic("A", "a", ["あ"])
        self.assertContains(self.client.get(reverse("learning:dashboard")), "data-loading-text")


class NavigationTests(LearningTestCase):
    """T3.4 — badge số từ đến hạn ở sidebar + tiêu đề trang dùng chung."""

    def test_sidebar_badge_shows_due_words(self):
        topic = self._make_topic("A", "a", ["あ", "い"])
        for vocab in topic.vocabularies.all():
            self._progress(vocab, due_offset=-1)
        response = self.client.get(reverse("vocabulary:index"))
        self.assertContains(response, '<span class="nav-badge"', count=1)
        self.assertEqual(str(response.context["due_badge"]), "2")

    def test_badge_is_cached_but_refreshed_after_grading(self):
        topic = self._make_topic("A", "a", ["あ"])
        progress = self._progress(topic.vocabularies.get(), due_offset=-1)
        self.assertEqual(services.get_due_badge_count(self.user), 1)
        # Đổi thẳng DB: cache vẫn giữ số cũ (tối đa 60 giây)...
        UserVocabularyProgress.objects.filter(pk=progress.pk).update(
            next_review_date=self.user.local_today() + timedelta(days=9)
        )
        self.assertEqual(services.get_due_badge_count(self.user), 1)
        # ...nhưng chấm một từ thì xoá cache ngay.
        progress.refresh_from_db()
        services.review_word(progress, 5)
        self.assertEqual(services.get_due_badge_count(self.user), 0)

    def test_no_badge_when_nothing_is_due(self):
        self.assertNotContains(self.client.get(reverse("learning:review")), '<span class="nav-badge"')

    def test_pages_share_the_page_header_with_a_breadcrumb(self):
        for name in ("learning:review", "vocabulary:index", "accounts:settings"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertTemplateUsed(response, "partials/page_header.html")
                self.assertContains(response, 'class="eyebrow page-crumbs"')


class StudyDeckTests(ReviewTestCase):
    """spec.md T4.3 — học liền mạch: bộ thẻ nhúng + lô lệnh gửi ngầm."""

    def setUp(self):
        super().setUp()
        self._make_topic("Họp hành", "hop-hanh", ["会議", "議事録", "資料"])
        self.words = {v.word: v for v in Vocabulary.objects.all()}
        self.client.post(reverse("learning:study_start"), {"topic": "hop-hanh", "limit": "0"})
        self.sid = self.client.session["study_session_id"]

    def _deck(self, **extra):
        return self.client.get(reverse("learning:study"), **extra).context["deck"]

    def _sync(self, ops, session=None):
        payload = {"session": self.sid if session is None else session, "ops": ops}
        return self.client.post(reverse("learning:study_sync"), {"payload": json.dumps(payload)})

    def _grade(self, seq, vocab_id, code="nho"):
        return {"seq": seq, "op": "grade", "vocab": vocab_id, "quality": code}

    # --- Bộ thẻ nhúng ---------------------------------------------------------

    def test_study_page_embeds_the_deck(self):
        response = self.client.get(reverse("learning:study"))
        deck = response.context["deck"]
        current = response.context["word"].pk
        self.assertEqual(deck["current"], current)
        self.assertEqual(deck["session"], self.sid)
        self.assertEqual(deck["seq"], 0)
        self.assertEqual(deck["queue"], self.client.session["study_queue"])
        self.assertEqual(set(deck["cards"]), {str(v.pk) for v in self.words.values()})
        card = deck["cards"][str(current)]
        self.assertEqual(card["word"], response.context["word"].word)
        self.assertEqual(card["state"], srs.NEW)
        self.assertIsNone(card["previews"])
        self.assertIn("{seen}", deck["text"]["progress"])
        self.assertContains(response, 'id="study-deck"')
        self.assertContains(response, "js/study_deck.js")
        self.assertContains(response, "data-card-extra")

    def test_partial_render_also_carries_the_deck(self):
        response = self.client.get(reverse("learning:study"), **PARTIAL)
        self.assertContains(response, 'id="study-deck"')

    def test_topic_flashcard_screen_has_no_deck(self):
        response = self.client.get(reverse("learning:flashcard", args=["hop-hanh"]))
        self.assertNotContains(response, 'id="study-deck"')

    def test_deck_cards_carry_previews_when_the_option_is_on(self):
        self.user.show_review_interval = True
        self.user.save(update_fields=["show_review_interval"])
        deck = self._deck()
        previews = deck["cards"][str(deck["current"])]["previews"]
        self.assertEqual(set(previews), {"quen", "kho", "nho", "de"})

    def test_deck_query_count_does_not_grow_with_the_number_of_cards(self):
        ids = [v.pk for v in self.words.values()]
        url = reverse("learning:study_cards")
        with CaptureQueriesContext(connection) as one:
            self.client.get(url, {"ids": str(ids[0])})
        with self.assertNumQueries(len(one.captured_queries)):
            self.client.get(url, {"ids": ",".join(map(str, ids))})

    # --- Lô lệnh --------------------------------------------------------------

    def test_sync_grade_matches_form_grading(self):
        vocab = self.words["会議"]
        response = self._sync([self._grade(1, vocab.pk, "quen")])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["seq"], 1)
        status = data["cards"][str(vocab.pk)]
        self.assertTrue(status["learning"])
        self.assertIsNotNone(status["due"])
        self.assertIn(vocab.pk, self.client.session["study_learning"])
        self.assertNotIn(vocab.pk, self.client.session["study_queue"])
        self.assertEqual(StudySession.objects.get(pk=self.sid).words_reviewed, 1)
        self.assertEqual(data["undo"], {"vocab": vocab.pk, "word": "会議"})

    def test_resent_ops_are_not_graded_twice(self):
        vocab = self.words["会議"]
        self._sync([self._grade(1, vocab.pk)])
        response = self._sync([self._grade(1, vocab.pk), self._grade(2, self.words["資料"].pk)])
        self.assertEqual(response.json()["seq"], 2)
        self.assertEqual(StudySession.objects.get(pk=self.sid).words_reviewed, 2)
        self.assertEqual(self._deck()["seq"], 2)

    def test_wrong_session_is_a_conflict(self):
        response = self._sync([self._grade(1, self.words["会議"].pk)], session=self.sid + 99)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(StudySession.objects.get(pk=self.sid).words_reviewed, 0)

    def test_logged_out_gets_401_json(self):
        self.client.logout()
        response = self._sync([self._grade(1, self.words["会議"].pk)])
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["login"], reverse("accounts:login"))

    def test_broken_payload_is_rejected(self):
        response = self.client.post(reverse("learning:study_sync"), {"payload": "{not json"})
        self.assertEqual(response.status_code, 400)
        response = self._sync([{"seq": "x", "op": "grade", "vocab": 1}])
        self.assertEqual(response.status_code, 400)

    def test_deleted_word_is_reported_missing(self):
        vocab = self.words["資料"]
        vocab_id = vocab.pk
        vocab.delete()
        data = self._sync([self._grade(1, vocab_id)]).json()
        self.assertEqual(data["missing"], [vocab_id])
        self.assertEqual(data["seq"], 1)

    def test_undo_op_restores_the_word(self):
        vocab = self.words["会議"]
        self._sync([self._grade(1, vocab.pk, "de")])
        data = self._sync([{"seq": 2, "op": "undo", "vocab": vocab.pk}]).json()
        self.assertFalse(data["resync"])
        self.assertIsNone(data["undo"])
        self.assertFalse(UserVocabularyProgress.objects.filter(user=self.user, vocabulary=vocab).exists())
        self.assertEqual(StudySession.objects.get(pk=self.sid).words_reviewed, 0)
        self.assertEqual(self.client.session["study_queue"][0], vocab.pk)
        # Thẻ vừa hoàn tác hiện lại ngay — như nút "Hoàn tác" cũ.
        self.assertEqual(self._deck()["current"], vocab.pk)

    def test_grade_then_undo_then_grade_equals_a_single_grade(self):
        vocab = self.words["会議"]
        self._sync([
            self._grade(1, vocab.pk, "quen"),
            {"seq": 2, "op": "undo", "vocab": vocab.pk},
            self._grade(3, vocab.pk, "de"),
        ])
        progress = UserVocabularyProgress.objects.get(user=self.user, vocabulary=vocab)
        self.assertEqual(progress.card_state, srs.REVIEW)
        self.assertEqual(StudySession.objects.get(pk=self.sid).words_reviewed, 1)
        self.assertNotIn(vocab.pk, self.client.session["study_learning"])

    def test_undo_that_does_not_match_asks_for_resync(self):
        self._sync([self._grade(1, self.words["会議"].pk)])
        data = self._sync([
            {"seq": 2, "op": "undo", "vocab": self.words["資料"].pk},
            self._grade(3, self.words["資料"].pk),
        ]).json()
        self.assertTrue(data["resync"])
        self.assertEqual(StudySession.objects.get(pk=self.sid).words_reviewed, 1)

    def test_whole_session_through_sync_ends_on_the_summary(self):
        deck = self._deck()
        ops = [self._grade(i + 1, vid, "de") for i, vid in enumerate(deck["queue"])]
        data = self._sync(ops).json()
        self.assertTrue(all(not s["learning"] for s in data["cards"].values()))
        response = self.client.get(reverse("learning:study"), **PARTIAL)
        self.assertIsNone(response.context["word"])
        self.assertEqual(response.context["summary"]["words"], 3)
        self.assertEqual(response.context["summary"]["percent"], 100)

    def test_new_session_resets_the_sequence(self):
        self._sync([self._grade(1, self.words["会議"].pk)])
        self.client.post(reverse("learning:study_start"), {"topic": "hop-hanh", "limit": "0"})
        self.assertEqual(self._deck()["seq"], 0)

    # --- Tải thêm thẻ / thảo luận ---------------------------------------------

    def test_cards_endpoint_skips_deleted_words(self):
        keep, gone = self.words["会議"], self.words["資料"]
        gone_id = gone.pk
        gone.delete()
        data = self.client.get(
            reverse("learning:study_cards"), {"ids": f"{keep.pk},{gone_id},abc"}
        ).json()
        self.assertEqual(list(data["cards"]), [str(keep.pk)])

    def test_discussion_endpoint_renders_comments(self):
        vocab = self.words["会議"]
        Contribution.objects.create(
            user=self.user, target_vocabulary=vocab,
            contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            status_code=STATUS_APPROVED, comment_text="Hay quá",
        )
        response = self.client.get(reverse("learning:study_discussion", args=[vocab.pk]))
        self.assertContains(response, "Hay quá")
        self.assertContains(response, 'name="next" value="%s"' % reverse("learning:study"))
        self.assertNotContains(response, "<html")
        deck = self._deck()
        self.assertEqual(deck["cards"][str(vocab.pk)]["comments"], 1)


class NewWordAllowanceTests(LearningTestCase):
    """spec.md T6.1 — một hạn mức từ mới cho MỌI lối vào."""

    def setUp(self):
        super().setUp()
        self.user.daily_review_goal = 3
        self.user.save(update_fields=["daily_review_goal"])
        self.topic = self._make_topic(
            "Nhiều từ", "nhieu-tu", [f"語{i:02d}" for i in range(10)]
        )
        self.words = list(self.topic.vocabularies.order_by("word"))

    def _learn(self, *vocabs):
        for vocab in vocabs:
            services.review_word(services.get_or_start_progress(self.user, vocab), 5)

    def _start(self, **data):
        data.setdefault("topic", "nhieu-tu")
        return self.client.post(reverse("learning:study_start"), data)

    def test_allowance_counts_new_words_learned_today(self):
        allowance = services.new_word_allowance(self.user)
        self.assertEqual((allowance.goal, allowance.learned_today, allowance.left), (3, 0, 3))
        self._learn(*self.words[:2])
        self.assertEqual(services.new_word_allowance(self.user).left, 1)
        self._learn(*self.words[2:5])
        self.assertEqual(services.new_word_allowance(self.user).left, 0)

    def test_undoing_a_first_grade_gives_the_word_back(self):
        page = reverse("learning:flashcard", args=["nhieu-tu"])
        word = self.client.get(page).context["word"]
        self.client.post(
            reverse("learning:flashcard_review", args=[word.pk]),
            {"quality": "nho", "topic_slug": "nhieu-tu"},
        )
        self.assertEqual(services.new_word_allowance(self.user).left, 2)
        self.client.post(reverse("learning:undo"))
        self.assertEqual(services.new_word_allowance(self.user).left, 3)

    def test_plan_keeps_due_words_and_caps_new_ones(self):
        due = self.words[9]
        self._progress(due, due_offset=-1)
        words = vocab_selectors.filter_vocabulary(self.user, topics=[self.topic])
        plan = services.plan_study_queue(self.user, words, new_limit=2)
        self.assertEqual(plan.queue, [due.pk, self.words[0].pk, self.words[1].pk])
        self.assertEqual(plan.held_new, 7)
        # Không truyền new_limit = hành vi cũ (SC15).
        self.assertEqual(len(services.build_study_queue(self.user, words)), 10)

    def test_held_new_only_counts_words_the_session_limit_would_have_taken(self):
        words = vocab_selectors.filter_vocabulary(self.user, topics=[self.topic])
        plan = services.plan_study_queue(self.user, words, limit=2, new_limit=3)
        self.assertEqual((len(plan.queue), plan.held_new), (2, 0))
        plan = services.plan_study_queue(self.user, words, limit=5, new_limit=3)
        self.assertEqual((len(plan.queue), plan.held_new), (3, 2))

    def test_sc05_start_caps_new_words_and_says_so(self):
        response = self._start(limit="0")
        self.assertRedirects(response, reverse("learning:study"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["study_queue"], [w.pk for w in self.words[:3]])
        page = self.client.get(reverse("learning:study"))
        self.assertContains(page, "giữ lại 7 từ mới")

    def test_sc05_start_with_only_new_words_past_the_cap_goes_back_to_the_filter(self):
        self._learn(*self._make_topic("Khác", "khac", ["他1", "他2", "他3"]).vocabularies.all())
        sessions = StudySession.objects.count()
        response = self._start(limit="0", status="new")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("vocabulary:index") + "?"))
        self.assertIn("topic=nhieu-tu", response["Location"])
        self.assertIn("status=new", response["Location"])
        self.assertEqual(StudySession.objects.count(), sessions)
        self.assertFalse(self.client.session.get("study_queue"))

    def test_over_limit_opens_exactly_one_more_allowance(self):
        self._learn(*self.words[7:])
        self._start(limit="0", status="new", over_limit="1")
        self.assertEqual(self.client.session["study_queue"], [w.pk for w in self.words[:3]])
        self._learn(*self.words[:3])
        self._start(limit="0", status="new", over_limit="1")
        self.assertEqual(self.client.session["study_queue"], [w.pk for w in self.words[3:6]])

    def test_sc05_shows_the_over_limit_notice_with_the_same_filter(self):
        self._learn(*self.words[7:])
        page = self.client.get(
            reverse("vocabulary:index"),
            {"topic": "nhieu-tu", "status": "new", "filtered": "1", "limit": "0"},
        )
        self.assertFalse(page.context["can_start"])
        notice = page.context["over_limit"]
        self.assertEqual((notice["learned"], notice["goal"], notice["extra"]), (3, 3, 3))
        self.assertIn(("over_limit", "1"), notice["hidden_fields"])
        self.assertIn(("topic", "nhieu-tu"), notice["hidden_fields"])
        self.assertIn(("status", "new"), notice["hidden_fields"])
        self.assertContains(page, "Vẫn học thêm 3 từ mới")

    def test_sc05_without_held_words_shows_no_notice(self):
        page = self.client.get(
            reverse("vocabulary:index"), {"topic": "nhieu-tu", "filtered": "1", "limit": "10"}
        )
        self.assertTrue(page.context["can_start"])
        self.assertEqual(page.context["held_new"], 7)
        self.assertEqual(page.context["start_count"], 3)
        self.assertContains(page, "Lượt này học 3 từ")
        self.user.daily_review_goal = 20
        self.user.save(update_fields=["daily_review_goal"])
        page = self.client.get(
            reverse("vocabulary:index"), {"topic": "nhieu-tu", "filtered": "1", "limit": "0"}
        )
        self.assertIsNone(page.context["over_limit"])
        self.assertNotContains(page, "Vẫn học thêm")

    def test_forecast_adds_the_extra_words_to_tomorrow(self):
        self._progress(self.words[9], due_offset=1)  # card_state mặc định "review"
        notice = services.over_limit_forecast(self.user, 3)
        self.assertEqual(notice["tomorrow"], 4)

    def test_sc04_done_screen_shows_the_forecast(self):
        self._learn(*self.words[:3])
        page = self.client.get(reverse("learning:flashcard", args=["nhieu-tu"]))
        self.assertIsNone(page.context["word"])
        self.assertEqual(page.context["over_limit"]["extra"], 3)
        self.assertContains(page, "Vẫn học thêm 3 từ mới")
        self.assertContains(page, reverse("learning:flashcard_more_new", args=["nhieu-tu"]))

    def test_sc15_review_is_not_capped(self):
        self._learn(*self.words[:3])
        for vocab in self.words[3:]:
            self._progress(vocab, due_offset=0)
        response = self.client.post(
            reverse("learning:review_start"), {"scope": "due", "limit": "0"}
        )
        self.assertRedirects(response, reverse("learning:study"))
        self.assertEqual(len(self.client.session["study_queue"]), 7)


class OvernightScheduleTests(TestCase):
    """srs.schedule(overnight=True) — spec.md T6.2 luật 3 (hàm thuần)."""

    def test_good_on_a_leftover_learning_word_graduates(self):
        card = srs.Card(state=srs.LEARNING, step=0)
        r = srs.schedule(card, srs.GOOD, overnight=True)
        self.assertEqual(r.card.state, srs.REVIEW)
        self.assertEqual(r.card.interval_days, srs.GRADUATE_INTERVAL)
        # Không có cờ: giữ luật cũ, sang bước 10 phút.
        r = srs.schedule(card, srs.GOOD)
        self.assertEqual((r.card.state, r.card.step), (srs.LEARNING, 1))

    def test_other_grades_keep_the_old_rules(self):
        card = srs.Card(state=srs.LEARNING, step=1)
        for quality in (srs.AGAIN, srs.HARD, srs.EASY):
            self.assertEqual(
                srs.schedule(card, quality, overnight=True),
                srs.schedule(card, quality),
            )

    def test_relearning_graduates_with_its_old_interval(self):
        card = srs.Card(state=srs.RELEARNING, step=0, interval_days=3)
        r = srs.schedule(card, srs.GOOD, overnight=True)
        self.assertEqual((r.card.state, r.card.interval_days), (srs.REVIEW, 3))

    def test_new_and_review_cards_ignore_the_flag(self):
        for card in (srs.Card(), srs.Card(state=srs.REVIEW, interval_days=6, repetitions=2)):
            self.assertEqual(
                srs.schedule(card, srs.GOOD, overnight=True), srs.schedule(card, srs.GOOD)
            )


class LeftoverLearningTests(LearningTestCase):
    """spec.md T6.2 — từ dở bước học khi rời phiên."""

    def setUp(self):
        super().setUp()
        self.topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約", "会計", "領収書"])
        self.words = {v.word: v for v in self.topic.vocabularies.all()}
        self.today = self.user.local_today()

    def _row(self, word):
        return UserVocabularyProgress.objects.get(user=self.user, vocabulary=self.words[word])

    def _start_study(self, **data):
        data.setdefault("topic", "nha-hang")
        data.setdefault("limit", "0")
        return self.client.post(reverse("learning:study_start"), data)

    def _grade_study(self, word, code="nho"):
        self.client.post(reverse("learning:study_review", args=[self.words[word].pk]), {"quality": code})

    def _leftover(self, word, *, days_ago=1, postponed=True):
        """Từ đang học bỏ dở `days_ago` ngày trước (postponed: đã hoãn bằng Kết thúc)."""
        return UserVocabularyProgress.objects.create(
            user=self.user, vocabulary=self.words[word], card_state=srs.LEARNING,
            learning_step=1,
            next_review_date=self.today - timedelta(days=0 if postponed else days_ago),
            due_at=None if postponed else timezone.now() - timedelta(days=days_ago),
        )

    # --- Kết thúc phiên -> hoãn sang mai ------------------------------------
    def test_ending_a_study_session_postpones_learning_words(self):
        self._start_study()
        self._grade_study("注文", "nho")    # bước 1 (10 phút) -> còn đang học
        self._grade_study("予約", "quen")   # bước 0 -> còn đang học
        self._grade_study("会計", "de")     # tốt nghiệp -> không đụng
        response = self.client.post(reverse("learning:study_end"), follow=True)

        tomorrow = self.today + timedelta(days=1)
        for word, step in (("注文", 1), ("予約", 0)):
            row = self._row(word)
            self.assertEqual((row.card_state, row.learning_step), (srs.LEARNING, step))
            self.assertEqual(row.next_review_date, tomorrow)
            self.assertIsNone(row.due_at)
        self.assertEqual(self._row("会計").card_state, srs.REVIEW)
        self.assertContains(response, "Đã hẹn 2 từ đang học dở sang ngày mai")

    def test_postponed_words_leave_today(self):
        self._start_study()
        self._grade_study("注文", "nho")
        self.assertIn(self.words["注文"].pk, services.build_daily_queue(self.user))
        self.assertEqual(services.count_due_today(self.user), 1)
        self.client.post(reverse("learning:study_end"))

        self.assertNotIn(self.words["注文"].pk, services.build_daily_queue(self.user))
        self.assertEqual(services.count_due_today(self.user), 0)
        self.assertEqual(services.count_due_tomorrow(self.user), 1)
        queue = services.get_topic_queue(self.user, self.topic)
        self.assertNotIn(self.words["注文"], queue.words)

    def test_starting_another_session_also_postpones(self):
        self._start_study()
        self._grade_study("注文", "nho")
        self._start_study()
        self.assertEqual(self._row("注文").next_review_date, self.today + timedelta(days=1))

    def test_extra_review_sessions_never_postpone(self):
        self._progress(self.words["注文"], due_offset=3)
        self.client.post(reverse("learning:study_retry"), {"vocab": [self.words["注文"].pk]})
        self.assertFalse(self.client.session["study_touch_schedule"])
        self._grade_study("注文", "quen")
        before = self._row("注文")
        self.client.post(reverse("learning:study_end"))
        after = self._row("注文")
        self.assertEqual(
            (after.next_review_date, after.card_state), (before.next_review_date, before.card_state)
        )

    def test_sc04_end_postpones_and_is_post_only(self):
        page = reverse("learning:flashcard", args=["nha-hang"])
        word = self.client.get(page).context["word"]
        self.client.post(
            reverse("learning:flashcard_review", args=[word.pk]),
            {"quality": "nho", "topic_slug": "nha-hang"},
        )
        end = reverse("learning:flashcard_end", args=["nha-hang"])
        self.assertContains(self.client.get(page), end)
        self.assertEqual(self.client.get(end).status_code, 405)
        self.assertRedirects(self.client.post(end), reverse("learning:dashboard"))
        row = UserVocabularyProgress.objects.get(user=self.user, vocabulary=word)
        self.assertEqual(row.next_review_date, self.today + timedelta(days=1))
        self.assertIsNone(row.due_at)
        self.assertIsNone(self.client.session.get("flashcard_session_id_nha-hang"))

    # --- Hôm sau: đứng đầu, đến hạn hôm nay, "Nhớ" là xong -------------------
    def test_leftover_words_come_first_in_the_daily_queue(self):
        self._progress(self.words["会計"], due_offset=-3)   # REVIEW quá hạn
        self._leftover("注文")                               # hoãn từ hôm qua
        self._leftover("予約", days_ago=2, postponed=False)  # bỏ ngang 2 hôm trước
        queue = services.build_daily_queue(self.user)
        self.assertEqual(
            queue[:3], [self.words["予約"].pk, self.words["注文"].pk, self.words["会計"].pk]
        )

    def test_leftover_words_lead_the_topic_queue(self):
        self._progress(self.words["会計"], due_offset=-3)
        self._leftover("注文")
        queue = services.get_topic_queue(self.user, self.topic)
        self.assertEqual(queue.words[:2], [self.words["注文"], self.words["会計"]])
        self.assertEqual((queue.n_review, queue.n_learning), (2, 0))

    def test_learning_words_from_today_stay_at_the_end(self):
        UserVocabularyProgress.objects.create(
            user=self.user, vocabulary=self.words["注文"], card_state=srs.LEARNING,
            next_review_date=self.today, due_at=timezone.now() - timedelta(minutes=1),
        )
        self._progress(self.words["会計"], due_offset=0)
        self.assertEqual(
            services.build_daily_queue(self.user)[:2],
            [self.words["会計"].pk, self.words["注文"].pk],
        )

    def test_leftover_words_count_as_due_today_not_overdue(self):
        self._leftover("注文", days_ago=2, postponed=False)
        self._leftover("予約")
        self._progress(self.words["会計"], due_offset=-1)
        overview = services.get_review_overview(self.user)
        self.assertEqual((overview["overdue"], overview["due_today"]), (1, 2))
        calendar = services.get_review_calendar(self.user)
        self.assertEqual((calendar[0]["count"], calendar[1]["count"]), (1, 2))
        self.assertEqual(services.count_due_today(self.user), 3)

    def test_good_on_a_leftover_word_graduates_it(self):
        row = self._leftover("注文")
        previews = services.grade_previews(row)
        self.assertEqual(previews[srs.GOOD], ("days", srs.GRADUATE_INTERVAL))
        result = services.review_word(row, srs.GOOD)
        self.assertFalse(result.in_session)
        row.refresh_from_db()
        self.assertEqual(row.card_state, srs.REVIEW)
        self.assertEqual(row.next_review_date, self.today + timedelta(days=srs.GRADUATE_INTERVAL))

    def test_a_word_learned_today_still_takes_its_steps(self):
        row = UserVocabularyProgress.objects.create(
            user=self.user, vocabulary=self.words["注文"], card_state=srs.LEARNING,
            learning_step=0, next_review_date=self.today,
            due_at=timezone.now() - timedelta(minutes=2),
        )
        self.assertTrue(services.review_word(row, srs.GOOD).in_session)

    def test_undo_after_ending_restores_the_old_schedule(self):
        self._start_study()
        self._grade_study("注文", "nho")
        row = self._row("注文")
        self.client.post(reverse("learning:study_end"))
        self.client.post(reverse("learning:undo"))
        self.assertFalse(
            UserVocabularyProgress.objects.filter(pk=row.pk).exists(),
            "hoàn tác lần chấm đầu của từ mới xoá dòng tiến độ",
        )


class SwipeUpMarkupTests(LearningTestCase):
    """spec.md T6.3 — vuốt lên = Dễ. Cử chỉ chạy ở main.js (kiểm thủ công bằng
    Chromium + CDP touch); ở đây chỉ chốt phần server dựng ra."""

    def test_study_screen_explains_the_three_swipes(self):
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        page = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        self.assertContains(page, "Vuốt thẻ: ← Quên rồi · → Nhớ · ↑ Dễ")
        self.assertContains(page, "vuốt trái Quên rồi · phải Nhớ · lên Dễ")
        # main.js tìm nút Dễ bằng data-grade-key="4".
        self.assertContains(page, 'value="de" data-grade-key="4"')

    def test_main_js_maps_swipe_up_to_the_easy_button(self):
        from pathlib import Path

        from django.conf import settings

        js = (Path(settings.BASE_DIR) / "static/js/main.js").read_text(encoding="utf-8")
        self.assertIn('var SWIPE_KEYS = { right: "3", left: "1", up: "4" };', js)


class GradeToastTests(LearningTestCase):
    """spec.md T6.4 — câu báo sau mỗi lần chấm (server dựng sẵn data-toast)."""

    def setUp(self):
        super().setUp()
        self.topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        self.words = {v.word: v for v in self.topic.vocabularies.all()}

    def _buttons(self, page):
        return {b["code"]: b for b in page.context["grade_buttons"]}

    def test_new_word_toasts_say_when_it_comes_back(self):
        page = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        toasts = {code: b["toast"] for code, b in self._buttons(page).items()}
        self.assertEqual(toasts["quen"], "✗ Quên rồi · gặp lại trong phiên này")
        self.assertEqual(toasts["kho"], "✓ Khó · gặp lại trong phiên này")
        self.assertEqual(toasts["nho"], "✓ Nhớ · gặp lại trong phiên này")
        self.assertEqual(toasts["de"], "✓ Dễ · gặp lại sau 4 ngày")
        self.assertContains(page, 'data-toast="✓ Dễ · gặp lại sau 4 ngày"')
        self.assertContains(page, "data-grade-toast")

    def test_toasts_do_not_depend_on_the_interval_setting(self):
        self.assertFalse(self.user.show_review_interval)
        page = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        buttons = self._buttons(page)
        self.assertEqual(buttons["de"]["delay"], "")          # không hiện dưới nút
        self.assertIn("4 ngày", buttons["de"]["toast"])       # nhưng câu báo vẫn có

    def test_review_word_toasts_show_days(self):
        progress = self._progress(self.words["予約"], due_offset=0)
        progress.interval_days, progress.srs_level = 6, 2
        progress.save()
        self._progress(self.words["注文"], due_offset=5)
        page = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        self.assertEqual(page.context["word"], self.words["予約"])
        toasts = {code: b["toast"] for code, b in self._buttons(page).items()}
        self.assertEqual(toasts["quen"], "✗ Quên rồi · gặp lại trong phiên này")
        self.assertEqual(toasts["nho"], "✓ Nhớ · gặp lại sau 15 ngày")

    def test_deck_cards_always_carry_toasts(self):
        self.client.post(reverse("learning:study_start"), {"topic": "nha-hang", "limit": "0"})
        page = self.client.get(reverse("learning:study"))
        deck = page.context["deck"]
        card = deck["cards"][str(deck["current"])]
        self.assertIsNone(card["previews"])                   # tuỳ chọn SC08 đang tắt
        self.assertEqual(card["toasts"]["de"], "✓ Dễ · gặp lại sau 4 ngày")

    def test_sync_returns_fresh_toasts_for_the_graded_card(self):
        self.client.post(reverse("learning:study_start"), {"topic": "nha-hang", "limit": "0"})
        deck = self.client.get(reverse("learning:study")).context["deck"]
        vocab = deck["current"]
        payload = {"session": deck["session"], "ops": [
            {"seq": 1, "op": "grade", "vocab": vocab, "quality": "nho"},
        ]}
        data = self.client.post(
            reverse("learning:study_sync"), {"payload": json.dumps(payload)}
        ).json()
        # Sau "Nhớ" lần đầu từ ở bước 10 phút -> "Nhớ" lần nữa là tốt nghiệp 1 ngày.
        self.assertEqual(data["cards"][str(vocab)]["toasts"]["nho"], "✓ Nhớ · gặp lại sau 1 ngày")

    def test_extra_review_toasts_say_the_schedule_is_unchanged(self):
        self._progress(self.words["注文"], due_offset=3)
        self.client.post(reverse("learning:study_retry"), {"vocab": [self.words["注文"].pk]})
        page = self.client.get(reverse("learning:study"))
        toasts = {code: b["toast"] for code, b in self._buttons(page).items()}
        self.assertEqual(toasts["nho"], "Nhớ · lượt ôn thêm, lịch ôn không đổi")
        card = page.context["deck"]["cards"][str(self.words["注文"].pk)]
        self.assertEqual(card["toasts"]["quen"], "Quên rồi · lượt ôn thêm, lịch ôn không đổi")


class BacklogAllowanceTests(LearningTestCase):
    """spec.md T6.5 — nợ ôn cao thì giảm / dừng từ mới. goal = 4 nên ngưỡng
    "chậm" = 12 (3 x 4), ngưỡng "dừng" = 20 (5 x 4)."""

    def setUp(self):
        super().setUp()
        self.user.daily_review_goal = 4
        self.user.save(update_fields=["daily_review_goal"])
        self.today = self.user.local_today()
        self.old = self._make_topic("Cũ", "cu", [f"旧{i:02d}" for i in range(30)])
        self.new = self._make_topic("Mới", "moi", [f"新{i:02d}" for i in range(10)])
        self.old_words = list(self.old.vocabularies.order_by("word"))

    def _due(self, count, **extra):
        """`count` từ ôn đến hạn hôm nay, học từ hôm trước (không tính là từ mới hôm nay)."""
        rows = [
            UserVocabularyProgress(
                user=self.user, vocabulary=vocab, card_state=srs.REVIEW,
                next_review_date=self.today, **extra,
            )
            for vocab in self.old_words[:count]
        ]
        UserVocabularyProgress.objects.bulk_create(rows)
        UserVocabularyProgress.objects.filter(user=self.user).update(
            created_at=timezone.now() - timedelta(days=3)
        )

    def _allowance(self):
        return services.new_word_allowance(self.user)

    def test_thresholds(self):
        for backlog, cap, paused, threshold in (
            (11, 4, False, 0), (12, 2, True, 12), (19, 2, True, 12), (20, 0, True, 20),
        ):
            UserVocabularyProgress.objects.filter(user=self.user).delete()
            self._due(backlog)
            a = self._allowance()
            self.assertEqual(
                (a.backlog, a.cap, a.left, a.paused, a.threshold),
                (backlog, cap, cap, paused, threshold), backlog,
            )

    def test_words_learned_today_still_count_against_the_reduced_cap(self):
        self._due(12)
        services.review_word(services.get_or_start_progress(self.user, self.new.vocabularies.first()), 5)
        a = self._allowance()
        self.assertEqual((a.cap, a.learned_today, a.left), (2, 1, 1))

    def test_backlog_ignores_today_learning_and_postponed_words(self):
        self._due(11)
        extra = self.old_words[11:14]
        UserVocabularyProgress.objects.create(   # đang học trong ngày
            user=self.user, vocabulary=extra[0], card_state=srs.LEARNING,
            next_review_date=self.today, due_at=timezone.now(),
        )
        UserVocabularyProgress.objects.create(   # đã hoãn sang mai
            user=self.user, vocabulary=extra[1], card_state=srs.LEARNING,
            next_review_date=self.today + timedelta(days=1), due_at=None,
        )
        self.assertEqual(self._allowance().backlog, 11)
        UserVocabularyProgress.objects.create(   # từ dở từ hôm trước -> là nợ
            user=self.user, vocabulary=extra[2], card_state=srs.LEARNING,
            next_review_date=self.today - timedelta(days=1), due_at=None,
        )
        self.assertEqual(self._allowance().backlog, 12)

    def test_reviewing_the_backlog_reopens_new_words(self):
        self._due(20)
        self.assertEqual(self._allowance().cap, 0)
        for row in UserVocabularyProgress.objects.filter(user=self.user)[:9]:
            services.review_word(row, srs.GOOD)
        self.assertEqual(self._allowance().cap, 4)   # còn 11 < 12

    def test_dashboard_explains_the_pause(self):
        self._due(20)
        page = self.client.get(reverse("learning:dashboard"))
        daily = page.context["daily"]
        self.assertEqual((daily["due"], daily["new"], daily["paused"]), (20, 0, True))
        self.assertContains(page, "Đang nợ 20 từ cần ôn — tạm dừng từ mới cho tới khi còn dưới 20 từ.")

    def test_dashboard_explains_the_slowdown(self):
        self._due(12)
        page = self.client.get(reverse("learning:dashboard"))
        self.assertEqual(page.context["daily"]["new"], 2)
        self.assertContains(
            page, "Đang nợ 12 từ cần ôn — hôm nay chỉ 2 từ mới; ôn xuống dưới 12 từ thì lại đủ 4 từ."
        )

    def test_dashboard_says_nothing_without_backlog(self):
        page = self.client.get(reverse("learning:dashboard"))
        self.assertFalse(page.context["daily"]["paused"])
        self.assertNotContains(page, "Đang nợ")

    def test_sc04_holds_new_words_and_explains_why(self):
        self._due(20)
        queue = services.get_topic_queue(self.user, self.new)
        self.assertEqual(queue.n_new, 0)
        self.assertTrue(queue.more_new)
        page = self.client.get(reverse("learning:flashcard", args=["moi"]))
        self.assertIsNone(page.context["word"])
        self.assertTrue(page.context["over_limit"]["paused"])
        self.assertContains(page, "tạm dừng từ mới")
        self.assertContains(page, "Vẫn học thêm 4 từ mới")

    def test_sc05_still_allows_learning_on_purpose(self):
        self._due(20)
        page = self.client.get(
            reverse("vocabulary:index"), {"topic": "moi", "filtered": "1", "limit": "0"}
        )
        self.assertFalse(page.context["can_start"])
        self.assertContains(page, "tạm dừng từ mới")
        self.client.post(
            reverse("learning:study_start"), {"topic": "moi", "limit": "0", "over_limit": "1"}
        )
        self.assertEqual(len(self.client.session["study_queue"]), 4)


class SwipeCoachTests(LearningTestCase):
    """spec.md T6.6 — hướng dẫn cử chỉ lần đầu. Hành vi (chỉ cảm ứng, sau lần
    lật đầu, 3 lần mở đầu, chạm để đóng) chạy ở main.js — kiểm thủ công bằng
    Chromium; ở đây chốt phần server dựng ra."""

    def setUp(self):
        super().setUp()
        self._make_topic("Nhà hàng", "nha-hang", ["注文"])

    def test_study_page_has_a_hidden_coach_outside_the_card_panel(self):
        page = self.client.get(reverse("learning:flashcard", args=["nha-hang"]))
        html = page.content.decode()
        self.assertIn('data-swipe-coach role="dialog" aria-labelledby="swipe-coach-title" hidden', html)
        # Ngoài #card-panel: thay thẻ bằng fetch không được xoá mất lớp phủ.
        self.assertGreater(html.index("data-swipe-coach"), html.index("data-grade-toast"))
        self.assertContains(page, "Vuốt thẻ để chấm điểm")
        self.assertContains(page, "Mỗi lần vuốt là một lần chấm — không phải chuyển trang.")

    def test_partial_response_does_not_repeat_the_coach(self):
        page = self.client.get(
            reverse("learning:flashcard", args=["nha-hang"]), HTTP_X_CARD_PARTIAL="1"
        )
        self.assertNotContains(page, "data-swipe-coach")

    def test_main_js_limits_the_coach_to_three_visits(self):
        from pathlib import Path

        from django.conf import settings

        js = (Path(settings.BASE_DIR) / "static/js/main.js").read_text(encoding="utf-8")
        self.assertIn('var COACH_STORAGE_KEY = "bjt.swipeCoach.count";', js)
        self.assertIn("var COACH_TIMES = 3;", js)
        self.assertIn('"(hover: none) and (pointer: coarse)"', js)
