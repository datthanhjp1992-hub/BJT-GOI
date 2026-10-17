from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core import dataio
from apps.core.constants import politeness_level_choices, practice_kind_choices

from .models import Drill, DrillItem, Lesson, PolitenessPhrase, Roleplay, RoleplayBlank, RoleplayLine, Unit


class LessonModelTests(TestCase):
    """T1 — docs/SPEC_LUYEN_TAP_BAI.md."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.unit = Unit.objects.create(number=1, name_jp="紹介", name_vi="Giới thiệu")
        cls.lesson = Lesson.objects.create(unit=cls.unit, scene_no=2, title_jp="よろしくお願いします")
        cls.drill = Drill.objects.create(lesson=cls.lesson, example_prompt_jp="山川物産、佐藤課長",
                                         example_answer_jp="こちら、山川物産の佐藤課長です。")
        cls.roleplay = Roleplay.objects.create(unit=cls.unit, number=1, situation_vi="Tự giới thiệu.")

    def assertDuplicateRejected(self, model, **fields):
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(**fields)

    def test_natural_keys_reject_duplicates(self):
        DrillItem.objects.create(drill=self.drill, number=1, prompt_jp="a", answer_jp="b")
        self.assertDuplicateRejected(DrillItem, drill=self.drill, number=1, prompt_jp="c", answer_jp="d")
        self.assertDuplicateRejected(Drill, lesson=self.lesson, example_prompt_jp="x", example_answer_jp="y")
        RoleplayBlank.objects.create(roleplay=self.roleplay, number=1, answer_jp="申します")
        self.assertDuplicateRejected(RoleplayBlank, roleplay=self.roleplay, number=1, answer_jp="x")
        PolitenessPhrase.objects.create(lesson=self.lesson, phrase_jp="ヤンと申します", level_code="1")
        self.assertDuplicateRejected(PolitenessPhrase, lesson=self.lesson, phrase_jp="ヤンと申します", level_code="2")

    def test_mastercode_seeded(self):
        self.assertEqual([c for c, _ in politeness_level_choices()], ["1", "2", "3"])
        self.assertEqual([c for c, _ in practice_kind_choices()], ["drill", "blank", "polite"])

    def test_every_model_has_audit_columns(self):
        for model in dataio.importable_models():
            if model._meta.app_label != "lessons":
                continue
            names = {f.name for f in model._meta.get_fields()}
            self.assertTrue(set(dataio.AUDIT_FIELDS) <= names, model)

    def test_import_columns_use_natural_keys(self):
        """Header CSV ở docs/data/lessons/ (T2) phụ thuộc thẳng vào đây."""
        self.assertEqual(dataio.headers_for(Lesson)[:2], ["unit__number", "scene_no"])
        self.assertEqual(dataio.headers_for(DrillItem)[:2], ["drill__lesson__scene_no", "number"])
        self.assertEqual(dataio.headers_for(RoleplayBlank)[:3], ["roleplay__unit__number", "roleplay__number", "number"])
        order = [dataio.model_label(m) for m in dataio.importable_models()]
        self.assertLess(order.index("lessons.unit"), order.index("lessons.lesson"))
        self.assertLess(order.index("lessons.drill"), order.index("lessons.drillitem"))


class CheckLessonDataTests(TestCase):
    """T2 — check_lesson_data bắt được dữ liệu lệch, không chỉ in "đạt"."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        unit = Unit.objects.create(number=1, name_jp="紹介")
        lesson = Lesson.objects.create(unit=unit, scene_no=1, title_jp="はじめまして")
        drill = Drill.objects.create(lesson=lesson, example_prompt_jp="a", example_answer_jp="b")
        for n in (1, 2, 3):
            DrillItem.objects.create(drill=drill, number=n, prompt_jp=f"p{n}", answer_jp=f"a{n}")
        for number in (1, 2):
            rp = Roleplay.objects.create(unit=unit, number=number, situation_vi="x")
            RoleplayLine.objects.create(roleplay=rp, number=1, speaker="A", text_jp="スミスです。{1}。")
            RoleplayBlank.objects.create(roleplay=rp, number=1, answer_jp="よろしくお願いします")
        PolitenessPhrase.objects.create(lesson=lesson, phrase_jp="ヤンと申します", level_code="1")
        PolitenessPhrase.objects.create(lesson=lesson, phrase_jp="ヤンといいます", level_code="2")
        cls.roleplay = rp

    def run_check(self):
        out = StringIO()
        try:
            call_command("check_lesson_data", "--no-expected", stdout=out)
        except SystemExit:
            return False, out.getvalue()
        return True, out.getvalue()

    def test_consistent_data_passes(self):
        ok, out = self.run_check()
        self.assertTrue(ok, out)

    def test_blank_without_answer_fails(self):
        RoleplayLine.objects.create(roleplay=self.roleplay, number=2, speaker="B", text_jp="{2}。")
        ok, out = self.run_check()
        self.assertFalse(ok)
        self.assertIn("lời thoại có [1, 2], đáp án có [1]", out)

    def test_short_drill_fails(self):
        DrillItem.objects.filter(number=3).delete()
        self.assertFalse(self.run_check()[0])
