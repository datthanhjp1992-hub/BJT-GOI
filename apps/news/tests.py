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
