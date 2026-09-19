"""
Test cho SC03_TrangChu và các hàm thống kê ở apps.learning.services.

Chạy: python manage.py test apps.learning
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.vocabulary import selectors as vocab_selectors
from apps.vocabulary.models import Topic, Vocabulary, VocabularyTopic
from apps.gamification.models import Contribution
from apps.gamification.services import (
    CONTRIBUTION_TYPE_COMMENT,
    STATUS_APPROVED,
    STATUS_PENDING,
)

from . import services
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
        self.assertEqual(response.context["in_progress"]["topic"], topic)
        self.assertContains(response, "Nhà hàng")
        # Nút "Học tiếp" phải trỏ đúng chủ đề đang học dở.
        self.assertContains(response, reverse("learning:flashcard", args=[topic.slug]))

    def test_renders_for_brand_new_user(self):
        """Chưa có dữ liệu gì thì trang chủ vẫn phải ra 200, không 500."""
        response = self.client.get(reverse("learning:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["in_progress"])


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
    def test_submitting_creates_a_pending_contribution(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        url = reverse("learning:flashcard_comment", args=[vocab.pk])

        self.client.post(url, {"comment_text": "Ghi chú test", "topic_slug": "nha-hang"})

        contribution = Contribution.objects.get(target_vocabulary=vocab)
        self.assertEqual(contribution.contribution_type_code, CONTRIBUTION_TYPE_COMMENT)
        self.assertEqual(contribution.status_code, STATUS_PENDING)
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

    def test_correct_answer_advances_next_review_date(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        vocab = topic.vocabularies.first()
        self.client.get(reverse("learning:quiz", args=["nha-hang"]))  # mở phiên
        url = reverse("learning:quiz_answer", args=["nha-hang", vocab.pk])

        response = self.client.post(url, {"choice": str(vocab.pk)})

        self.assertRedirects(response, reverse("learning:quiz", args=["nha-hang"]))
        progress = UserVocabularyProgress.objects.get(user=self.user, vocabulary=vocab)
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
        self.client.post(url, {"choice": str(vocab.pk)})

        response = self.client.get(reverse("learning:quiz", args=["nha-hang"]))

        session = StudySession.objects.get(user=self.user, topic=topic, session_type="quiz")
        self.assertIsNotNone(session.ended_at)
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
        self.assertTrue(vocab_selectors.touches_schedule(vocab_selectors.SCOPE_LEECH))
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
