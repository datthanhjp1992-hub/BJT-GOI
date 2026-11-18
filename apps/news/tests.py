from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core import dataio
from apps.core.constants import practice_kind_choices

from .models import NewsLesson, NewsSegment


class NewsModelTests(TestCase):
    """Task 2 — docs/SPEC_NGHE_BAN_TIN.md mục 3."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.lesson = NewsLesson.objects.create(number=1, title_jp="お歳暮商戦")

    def test_natural_keys_reject_duplicates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            NewsLesson.objects.create(number=1, title_jp="x")
        NewsSegment.objects.create(lesson=self.lesson, number=1, text_jp="a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            NewsSegment.objects.create(lesson=self.lesson, number=1, text_jp="b")

    def test_mastercode_has_news(self):
        self.assertEqual([c for c, _ in practice_kind_choices()], ["drill", "blank", "polite", "news"])

    def test_dataio_headers(self):
        self.assertEqual(dataio.headers_for(NewsSegment)[:2], ["lesson__number", "number"])
        self.assertEqual(dataio.headers_for(NewsLesson)[0], "number")


class HighlightTests(TestCase):
    """Task 3 — spec mục 6."""

    def test_splits_text_on_terms(self):
        from .services import highlight
        self.assertEqual(highlight("原料コストが高騰", [("原料", 1), ("高騰", 2)]),
                         [("原料", 1), ("コストが", None), ("高騰", 2)])

    def test_longest_term_wins(self):
        from .services import highlight
        self.assertEqual(highlight("生産拠点を", [("生産拠点", 1), ("生産", 2)]), [("生産拠点", 1), ("を", None)])

    def test_parts_rejoin_to_original_text(self):
        from .services import highlight
        text = "A<b>&B高騰する。"
        self.assertEqual("".join(p for p, _ in highlight(text, [("高騰", 1)])), text)

    def test_vocab_terms_filters_short_and_strips_suru(self):
        from apps.vocabulary.models import Vocabulary
        from .services import vocab_terms
        for w, r in (("高騰する", "こうとうする"), ("うち", "うち"), ("うちうち", "うちうち"), ("株", "かぶ")):
            Vocabulary.objects.create(word=w, reading=r, meaning_vi="x")
        terms = [t for t, _ in vocab_terms()]
        self.assertIn("高騰", terms)
        self.assertIn("うちうち", terms)
        self.assertNotIn("うち", terms)
        self.assertNotIn("株", terms)
        self.assertEqual(terms, sorted(terms, key=len, reverse=True))


class NewsViewTests(TestCase):
    """Task 4 — spec mục 5 + Review Focus của kế hoạch."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        call_command("seed_mastercode", verbosity=0)
        cls.user = get_user_model().objects.create_user(username="dat", password="MatKhauRatManh123")
        cls.l1 = NewsLesson.objects.create(number=1, title_jp="お歳暮商戦、本格スタート", title_vi="Mùa quà cuối năm")
        NewsLesson.objects.create(number=2, title_jp="東京株式市場続落")
        NewsSegment.objects.create(lesson=cls.l1, number=1, text_jp="A<b>B百貨店", translation_vi="Bản dịch 1")

    def setUp(self):
        self.client.force_login(self.user)

    def _url(self, name, *args):
        from django.urls import reverse
        return reverse(f"news:{name}", args=args)

    def test_login_required(self):
        self.client.logout()
        for url in (self._url("index"), self._url("lesson", 1), self._url("mark", 1)):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code if "danh-dau" not in url
                                 else self.client.post(url).status_code, 302)

    def test_index_lists_lessons_and_done_count(self):
        from apps.core.constants import PRACTICE_KIND_NEWS
        from apps.lessons.models import UserPracticeMark
        UserPracticeMark.objects.create(user=self.user, kind=PRACTICE_KIND_NEWS, object_id=self.l1.id, is_known=True)
        r = self.client.get(self._url("index"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "お歳暮商戦、本格スタート")
        self.assertEqual((r.context["done_count"], r.context["total"]), (1, 2))

    def test_missing_lesson_is_404(self):
        self.assertEqual(self.client.get(self._url("lesson", 99)).status_code, 404)

    def test_lesson_escapes_text_and_flags_missing_audio(self):
        from apps.core.properties import label
        r = self.client.get(self._url("lesson", 1))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "A&lt;b&gt;B")
        self.assertContains(r, label("news.no_audio"))
        self.assertEqual((r.context["prev_number"], r.context["next_number"]), (None, 2))

    def test_mark_is_explicit_not_toggle(self):
        from apps.core.constants import PRACTICE_KIND_NEWS
        from apps.lessons.models import UserPracticeMark
        for _ in range(2):
            r = self.client.post(self._url("mark", 1), {"done": "1"})
            self.assertRedirects(r, self._url("lesson", 1))
        mark = UserPracticeMark.objects.get(user=self.user, kind=PRACTICE_KIND_NEWS, object_id=self.l1.id)
        self.assertTrue(mark.is_known)
        self.client.post(self._url("mark", 1), {"done": "0"})
        mark.refresh_from_db()
        self.assertFalse(mark.is_known)
        self.assertEqual(self.client.get(self._url("mark", 1)).status_code, 405)
