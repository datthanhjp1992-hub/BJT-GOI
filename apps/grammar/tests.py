"""
Test app grammar -- importer + trang danh sách.

Chay: python manage.py test apps.grammar
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import importer
from .models import GrammarPattern

User = get_user_model()
CSV = settings.BASE_DIR / "docs" / "data" / "grammar" / "grammar_pattern.csv"


class ImporterTests(TestCase):
    def test_real_csv_is_valid_and_reimport_is_idempotent(self):
        rows = importer.read_rows(CSV)
        self.assertEqual(len(rows), 500)
        self.assertEqual(importer.validate(rows), [])
        self.assertEqual(importer.apply_rows(rows), (500, 0, 0))
        self.assertEqual(importer.apply_rows(rows), (0, 0, 500))

    def test_changed_row_is_updated(self):
        rows = [{"pattern": "〜につけ", "meaning_vi": "mỗi khi", "level": "N2"}]
        importer.apply_rows(rows)
        rows[0]["meaning_vi"] = "cứ hễ"
        self.assertEqual(importer.apply_rows(rows), (0, 1, 0))
        self.assertEqual(GrammarPattern.objects.get().meaning_vi, "cứ hễ")

    def test_validate_flags_duplicate_and_missing(self):
        rows = [{"pattern": "A", "meaning_vi": "x"}, {"pattern": "A", "meaning_vi": "y"}, {"pattern": "", "meaning_vi": "z"}]
        self.assertEqual([line for line, _ in importer.validate(rows)], [3, 4])


class IndexViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        GrammarPattern.objects.create(pattern="〜につけ", meaning_vi="mỗi khi", level="N2", category="対象")
        GrammarPattern.objects.create(pattern="〜をよそに", meaning_vi="bất chấp", level="N1", category="無関係")

    def setUp(self):
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("grammar:index")).status_code, 302)

    def test_index_shows_chapters_in_book_order_not_patterns(self):
        resp = self.client.get(reverse("grammar:index"))
        self.assertEqual([c["jp"] for c in resp.context["chapters"]], ["対象", "無関係"])
        self.assertEqual(resp.context["chapters"][0]["vi"], "Đối tượng")
        self.assertNotContains(resp, "〜につけ")

    def test_chapter_page_lists_only_that_chapter_with_next_link(self):
        resp = self.client.get(reverse("grammar:chapter", args=["対象"]))
        self.assertContains(resp, "〜につけ")
        self.assertNotContains(resp, "〜をよそに")
        self.assertEqual(resp.context["next"], "無関係")
        self.assertIsNone(resp.context["prev"])

    def test_unknown_chapter_404(self):
        self.assertEqual(self.client.get(reverse("grammar:chapter", args=["xyz"])).status_code, 404)

    def test_search_spans_all_chapters(self):
        resp = self.client.get(reverse("grammar:index"), {"q": "bất chấp"})
        self.assertContains(resp, "〜をよそに")
        self.assertNotContains(resp, "〜につけ")
