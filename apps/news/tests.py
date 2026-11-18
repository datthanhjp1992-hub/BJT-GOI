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
