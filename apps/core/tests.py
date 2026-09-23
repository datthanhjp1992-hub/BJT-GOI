"""
Test dùng chung cho toàn bộ template.

Chạy: python manage.py test apps.core
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.vocabulary.models import Topic

User = get_user_model()

# Dấu hiệu template chưa được xử lý mà lọt ra HTML.
TEMPLATE_MARKERS = ("{#", "#}", "{%", "{{")


class TemplateLeakTests(TestCase):
    """Không trang nào được để lọt cú pháp template ra HTML.

    Bẫy thật đã dính: `{# ... #}` của Django CHỈ có tác dụng trên MỘT dòng.
    Chú thích viết tràn nhiều dòng bằng `{# #}` không được coi là chú thích —
    Django in nguyên văn nó ra trang, và còn thực thi mọi `{{ biến }}` nằm bên
    trong. Chú thích nhiều dòng phải dùng `{% comment %}...{% endcomment %}`.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        Topic.objects.create(name="Nhà hàng", slug="nha-hang")

    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_user(
            username="dat", password="MatKhauRatManh123", is_staff=True,
        )

    def _assert_clean(self, url, response):
        html = response.content.decode()
        for marker in TEMPLATE_MARKERS:
            self.assertNotIn(
                marker, html,
                msg=f'{url} còn sót cú pháp template "{marker}" trong HTML trả về',
            )

    def test_anonymous_pages_render_clean(self):
        for url in (reverse("accounts:login"), reverse("accounts:register")):
            with self.subTest(url=url):
                self._assert_clean(url, self.client.get(url))

    def test_authenticated_pages_render_clean(self):
        self.client.force_login(self.staff)
        urls = [
            reverse("learning:dashboard"),
            reverse("vocabulary:index"),
            reverse("vocabulary:list", args=["nha-hang"]),
            reverse("learning:flashcard", args=["nha-hang"]),
            reverse("learning:quiz", args=["nha-hang"]),
            reverse("learning:review"),
            reverse("practice_sheets:create"),
            reverse("accounts:profile"),
            reverse("accounts:settings"),
            reverse("admin_panel:overview"),
            reverse("admin_panel:data_index"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, msg=url)
                self._assert_clean(url, response)


class KeepAliveTests(TestCase):
    """Tự ping giữ Render free thức — SiteSetting, /healthz/, màn Cài đặt hệ thống."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.url = reverse("admin_panel:system_settings")
        self.staff = User.objects.create_user(
            username="quantri_ka", password="MatKhauRatManh123", is_staff=True,
        )
        self.learner = User.objects.create_user(
            username="nguoihoc_ka", password="MatKhauRatManh123",
        )

    def test_healthz_no_login_no_db(self):
        with self.assertNumQueries(0):
            resp = self.client.get(reverse("healthz"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    def test_singleton_defaults(self):
        from apps.core.models import SiteSetting

        cfg = SiteSetting.load()
        self.assertEqual(cfg.pk, 1)
        self.assertTrue(cfg.keepalive_enabled)
        self.assertEqual(cfg.keepalive_interval_minutes, 5)
        cfg.keepalive_enabled = False
        cfg.save()
        self.assertFalse(SiteSetting.load().keepalive_enabled)
        self.assertEqual(SiteSetting.objects.count(), 1)

    def test_bad_interval_code_falls_back_to_5(self):
        from apps.core.models import SiteSetting

        cfg = SiteSetting.load()
        for code in ("abc", "0", "15", "60"):
            cfg.keepalive_interval_code = code
            self.assertEqual(cfg.keepalive_interval_minutes, 5)

    def test_learner_forbidden(self):
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_can_view_and_save(self):
        from apps.core.models import SiteSetting

        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'value="10"')
        resp = self.client.post(self.url, {"keepalive_interval_code": "10"})
        self.assertRedirects(resp, self.url)
        cfg = SiteSetting.load()
        self.assertFalse(cfg.keepalive_enabled)  # checkbox bỏ trống = tắt
        self.assertEqual(cfg.keepalive_interval_minutes, 10)
        self.assertEqual(cfg.updated_by_id, self.staff.pk)

        self.client.post(self.url, {"keepalive_enabled": "on", "keepalive_interval_code": "3"})
        cfg = SiteSetting.load()
        self.assertTrue(cfg.keepalive_enabled)
        self.assertEqual(cfg.keepalive_interval_minutes, 3)

    def test_reject_unknown_interval(self):
        self.client.force_login(self.staff)
        resp = self.client.post(self.url, {"keepalive_enabled": "on", "keepalive_interval_code": "30"})
        self.assertEqual(resp.status_code, 200)  # form lỗi, không redirect

    def test_start_is_noop_without_url(self):
        from apps.core import keepalive

        with self.settings(KEEPALIVE_URL=""):
            keepalive.start()
            self.assertFalse(keepalive._started)

    def test_record_result_keeps_updated_by(self):
        from apps.core import keepalive
        from apps.core.models import SiteSetting

        self.client.force_login(self.staff)
        self.client.post(self.url, {"keepalive_enabled": "on", "keepalive_interval_code": "5"})
        keepalive.record_result(True, "HTTP 200 · 12 ms")
        cfg = SiteSetting.load()
        self.assertTrue(cfg.keepalive_last_ok)
        self.assertEqual(cfg.keepalive_last_status, "HTTP 200 · 12 ms")
        self.assertIsNotNone(cfg.keepalive_last_ping_at)
        self.assertEqual(cfg.updated_by_id, self.staff.pk)
