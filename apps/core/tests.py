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
