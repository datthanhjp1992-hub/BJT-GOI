"""
Test cho SC07_QuanTriAdmin.

Chạy: python manage.py test apps.admin_panel
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.properties import label
from apps.gamification.models import Contribution
from apps.vocabulary.models import Topic, Vocabulary

from .views import CONTRIBUTION_STATUS_PENDING

User = get_user_model()


class AdminPanelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.url = reverse("admin_panel:overview")
        self.staff = User.objects.create_user(
            username="quantri", password="MatKhauRatManh123", is_staff=True,
            first_name="Nguyễn Thành Đạt",
        )
        self.learner = User.objects.create_user(
            username="nguoihoc", password="MatKhauRatManh123",
        )


class AccessTests(AdminPanelTestCase):
    def test_anonymous_is_sent_to_login(self):
        self.assertRedirects(
            self.client.get(self.url), reverse("accounts:login") + "?next=" + self.url
        )

    def test_normal_user_gets_403_not_a_redirect(self):
        """403 chứ không redirect: bị đá về trang đăng nhập khi đang đăng nhập
        khiến người dùng tưởng mình vừa bị đăng xuất."""
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_can_open(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin_panel/overview.html")


class OverviewContentTests(AdminPanelTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_stats_are_real_numbers(self):
        topic = Topic.objects.create(name="Nhà hàng", slug="nha-hang")
        vocab = Vocabulary.objects.create(
            word="予約", reading="よやく", meaning_vi="đặt chỗ", bjt_level="J4",
        )
        Contribution.objects.create(
            user=self.learner, contribution_type_code="001",
            status_code=CONTRIBUTION_STATUS_PENDING, target_vocabulary=vocab,
        )
        Contribution.objects.create(
            user=self.learner, contribution_type_code="001",
            status_code="002",  # đã duyệt -> không được đếm
            target_vocabulary=vocab,
        )
        # Tài khoản bị khoá không tính vào "người dùng hoạt động".
        User.objects.create_user(username="bikhoa", password="x", is_active=False)

        stats = self.client.get(self.url).context["stats"]
        self.assertEqual(stats["active_users"], 2)          # staff + learner
        self.assertEqual(stats["total_vocabulary"], 1)
        self.assertEqual(stats["total_topics"], 1)
        self.assertEqual(stats["pending_contributions"], 1)
        self.assertEqual(topic.slug, "nha-hang")

    def test_recent_users_are_newest_first_and_capped(self):
        from .views import RECENT_USER_LIMIT

        for i in range(RECENT_USER_LIMIT + 3):
            User.objects.create_user(username="hv%02d" % i, password="x")
        rows = self.client.get(self.url).context["recent_users"]
        self.assertEqual(len(rows), RECENT_USER_LIMIT)
        usernames = [u.get_username() for u in rows]
        self.assertEqual(usernames, sorted(usernames, reverse=True))

    def test_sidebar_links_to_django_admin(self):
        """Màn này cố tình không tự viết CRUD — nếu ai đó đổi hướng, test đỏ."""
        response = self.client.get(self.url)
        for url_name in (
            "admin:accounts_user_changelist",
            "admin:vocabulary_vocabulary_changelist",
            "admin:vocabulary_topic_changelist",
            "admin:gamification_contribution_changelist",
        ):
            self.assertContains(response, reverse(url_name))

    def test_greeting_uses_full_name(self):
        self.assertContains(self.client.get(self.url), "Nguyễn Thành Đạt")


class TopbarLinkTests(AdminPanelTestCase):
    def test_link_visible_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("learning:dashboard"))
        self.assertContains(response, reverse("admin_panel:overview"))
        self.assertContains(response, label("common.nav.admin"))

    def test_link_hidden_for_normal_user(self):
        self.client.force_login(self.learner)
        response = self.client.get(reverse("learning:dashboard"))
        self.assertNotContains(response, reverse("admin_panel:overview"))
