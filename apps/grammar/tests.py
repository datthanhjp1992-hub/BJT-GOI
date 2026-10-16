"""
Test app grammar -- importer + trang danh sách.

Chay: python manage.py test apps.grammar
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import importer
from . import services
from .models import GrammarPattern, UserGrammarProgress

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

    def test_chapter_page_shows_one_pattern_at_a_time(self):
        resp = self.client.get(reverse("grammar:chapter", args=["対象"]))
        self.assertEqual(resp.context["pattern"].pattern, "〜につけ")
        self.assertEqual((resp.context["i"], resp.context["total"]), (1, 1))
        self.assertNotContains(resp, "〜をよそに")

    def test_unknown_chapter_404(self):
        self.assertEqual(self.client.get(reverse("grammar:chapter", args=["xyz"])).status_code, 404)

    def test_search_spans_all_chapters(self):
        resp = self.client.get(reverse("grammar:index"), {"q": "bất chấp"})
        self.assertContains(resp, "〜をよそに")
        self.assertNotContains(resp, "〜につけ")


class QuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        cls.a = GrammarPattern.objects.create(pattern="〜につけ(て)", meaning_vi="mỗi khi", category="対象",
                                              example_jp="何かにつけて文句を言う。", display_order=1)
        cls.b = GrammarPattern.objects.create(pattern="〜について", meaning_vi="về việc", category="対象",
                                              example_jp="方針について話す。", display_order=2)
        cls.c = GrammarPattern.objects.create(pattern="〜ぬきで", meaning_vi="bỏ qua", category="対象",
                                              example_jp="仕事の話は抜きにして。", display_order=3)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("grammar:quiz", args=["対象"])
        self.answer_url = reverse("grammar:quiz_answer", args=["対象"])

    def test_question_cloze_blanks_pattern_and_falls_back_to_meaning(self):
        chapter = [self.a, self.b, self.c]
        q = services.build_question(self.a, chapter)
        self.assertEqual((q["kind"], q["prompt"]), ("cloze", "何か（　　）て文句を言う。"))
        self.assertEqual(sorted(o["id"] for o in q["options"]), sorted(p.id for p in chapter))
        self.assertEqual(services.build_question(self.c, chapter)["kind"], "meaning")
        self.assertEqual(q, services.build_question(self.a, chapter))  # tải lại không đổi thứ tự

    def test_correct_answer_masters_wrong_answer_unmasters(self):
        self.client.get(self.url, {"moi": 1})
        self.client.post(self.answer_url, {"i": 1, "option": self.a.id})
        self.client.post(self.answer_url, {"i": 2, "option": self.a.id})
        mastered = dict(UserGrammarProgress.objects.values_list("pattern_id", "is_mastered"))
        self.assertEqual(mastered, {self.a.id: True, self.b.id: False})

    def test_answer_twice_is_graded_once(self):
        self.client.get(self.url, {"moi": 1})
        self.client.post(self.answer_url, {"i": 1, "option": self.a.id})
        self.client.post(self.answer_url, {"i": 1, "option": self.b.id})
        p = UserGrammarProgress.objects.get(pattern=self.a)
        self.assertEqual((p.is_mastered, p.correct_count, p.wrong_count), (True, 1, 0))

    def test_result_lists_wrong_and_index_shows_progress(self):
        self.client.get(self.url, {"moi": 1})
        self.client.post(self.answer_url, {"i": 1, "option": self.a.id})
        self.client.post(self.answer_url, {"i": 2, "option": self.c.id})
        resp = self.client.get(self.url, {"i": 4})
        self.assertEqual(resp.context["score"], 1)
        self.assertEqual([p.id for _, p in resp.context["wrong"]], [self.b.id, self.c.id])
        tile = self.client.get(reverse("grammar:index")).context["chapters"][0]
        self.assertEqual((tile["mastered"], tile["count"]), (1, 3))

    def test_bad_post_redirects_without_grading(self):
        resp = self.client.post(self.answer_url, {"i": 99, "option": "x"})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(UserGrammarProgress.objects.exists())
