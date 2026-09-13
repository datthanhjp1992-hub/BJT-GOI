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

from apps.vocabulary.models import Topic, Vocabulary, VocabularyTopic

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

    def _make_topic(self, name, slug, words, level="J4"):
        topic = Topic.objects.create(name=name, slug=slug)
        for word in words:
            vocab = Vocabulary.objects.create(
                word=word, reading=word, meaning_vi="nghĩa " + word, bjt_level=level,
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
        self.assertEqual(result["level_code"], "J4")

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
        self.assertEqual(suggested[0].level_code, "J4")

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
