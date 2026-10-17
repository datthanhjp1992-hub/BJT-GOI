import random
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse, reverse_lazy

from apps.core import dataio
from apps.core.constants import PRACTICE_KIND_POLITE, politeness_level_choices, practice_kind_choices

from . import services, views
from .models import (
    Drill, DrillItem, Lesson, PolitenessPhrase, Roleplay, RoleplayBlank, RoleplayLine, Unit, UserPracticeMark,
)


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


class PracticeViewTestCase(TestCase):
    """Dữ liệu chung cho L1/L4: 2 chương, 12 bài có cặp lịch sự (chương 1: bài 1-6, chương 5: bài 7-12)."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        call_command("seed_mastercode", verbosity=0)
        cls.user = get_user_model().objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        cls.u1 = Unit.objects.create(number=1, name_jp="紹介する", name_vi="Giới thiệu")
        cls.u5 = Unit.objects.create(number=5, name_jp="依頼する", name_vi="Nhờ vả")
        cls.lessons = []
        for n in range(1, 13):
            lesson = Lesson.objects.create(unit=cls.u1 if n <= 6 else cls.u5, scene_no=n, title_jp=f"課{n}",
                                           title_vi=f"Bài {n}")
            PolitenessPhrase.objects.create(lesson=lesson, phrase_jp=f"丁寧{n}でございます", level_code="1")
            PolitenessPhrase.objects.create(lesson=lesson, phrase_jp=f"普通{n}だよ", level_code="3")
            cls.lessons.append(lesson)
        Roleplay.objects.create(unit=cls.u1, number=1, situation_vi="x")

    def setUp(self):
        self.client.force_login(self.user)


class PoliteServiceTests(PracticeViewTestCase):
    def test_pairs_skip_lessons_without_two_levels(self):
        odd = Lesson.objects.create(unit=self.u1, scene_no=40, title_jp="x")
        PolitenessPhrase.objects.create(lesson=odd, phrase_jp="一つだけ", level_code="2")
        found = services.pairs()
        self.assertNotIn(odd.id, found)
        formal, casual = found[self.lessons[0].id]
        self.assertEqual((formal.level_code, casual.level_code), ("1", "3"))

    def test_round_puts_wrong_pairs_first_then_unseen(self):
        wrong, right = self.lessons[3], self.lessons[4]
        services.record(self.user, PRACTICE_KIND_POLITE, services.pairs([wrong])[wrong.id][0].id, False)
        for lesson in self.lessons[:11]:
            if lesson != wrong:
                services.record(self.user, PRACTICE_KIND_POLITE, services.pairs([lesson])[lesson.id][0].id, True)
        state = services.build_round(self.user, "all", rng=random.Random(1))
        self.assertEqual(len(state["ids"]), services.ROUND_SIZE)
        self.assertEqual(state["ids"][0], wrong.id)            # đang sai -> hỏi trước
        self.assertEqual(state["ids"][1], self.lessons[11].id)  # chưa làm -> kế tiếp
        self.assertNotIn(right.id, state["ids"][:2])

    def test_round_respects_unit_group(self):
        state = services.build_round(self.user, "5-8")
        self.assertEqual(set(state["ids"]), {l.id for l in self.lessons[6:]})


class PoliteViewTests(PracticeViewTestCase):
    url = reverse_lazy("lessons:polite")

    def answer(self, i, formal):
        state = self.client.session[views.SESSION_KEY]
        q = services.round_question(state, i)
        option = q["formal"] if formal else q["casual"]
        return self.client.post(reverse("lessons:polite_answer"), {"i": i, "option": option.id}), q

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.get(reverse("lessons:index")).status_code, 302)

    def test_correct_answer_marks_known_and_refresh_does_not_rescore(self):
        self.client.get(self.url)
        resp, q = self.answer(1, formal=True)
        self.assertRedirects(resp, f"{self.url}?chuong=all&i=1")
        mark = UserPracticeMark.objects.get(user=self.user, kind=PRACTICE_KIND_POLITE, object_id=q["formal"].id)
        self.assertEqual((mark.is_known, mark.times), (True, 1))
        self.answer(1, formal=False)  # gửi lại cùng câu: không chấm lại
        mark.refresh_from_db()
        self.assertEqual((mark.is_known, mark.times), (True, 1))
        page = self.client.get(f"{self.url}?chuong=all&i=1")
        self.assertTrue(page.context["answered"])
        self.assertContains(page, q["formal"].phrase_jp)

    def test_wrong_answer_and_result_page(self):
        self.client.get(self.url)
        _, q = self.answer(1, formal=False)
        self.assertFalse(UserPracticeMark.objects.get(object_id=q["formal"].id).is_known)
        resp = self.client.get(f"{self.url}?chuong=all&i=99")
        self.assertTrue(resp.context["result"])
        self.assertEqual(resp.context["score"], 0)
        self.assertEqual(len(resp.context["items"]), services.ROUND_SIZE)

    def test_changing_group_starts_new_round(self):
        self.client.get(self.url)
        self.client.get(f"{self.url}?chuong=1-4")
        state = self.client.session[views.SESSION_KEY]
        self.assertEqual(state["group"], "1-4")
        self.assertEqual(set(state["ids"]), {l.id for l in self.lessons[:6]})

    def test_empty_group(self):
        resp = self.client.get(f"{self.url}?chuong=9-12")
        self.assertTrue(resp.context["empty"])

    def test_bad_post_is_ignored(self):
        resp = self.client.post(reverse("lessons:polite_answer"), {"i": "x", "option": "1"})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(UserPracticeMark.objects.exists())


class IndexViewTests(PracticeViewTestCase):
    def test_units_and_open_unit_follow_progress(self):
        resp = self.client.get(reverse("lessons:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([u["unit"].number for u in resp.context["units"]], [1, 5])
        self.assertEqual(resp.context["open_unit"], 1)
        self.assertEqual(resp.context["stats"]["polite_total"], 12)
        for lesson in self.lessons[:6]:
            services.record(self.user, PRACTICE_KIND_POLITE, services.pairs([lesson])[lesson.id][0].id, True)
        resp = self.client.get(reverse("lessons:index"))
        self.assertEqual(resp.context["open_unit"], 5)
        self.assertEqual(resp.context["stats"]["polite_known"], 6)
        self.assertContains(resp, 'href="/bai/lich-su/?chuong=5-8"')

    def test_sidebar_has_lessons_group(self):
        resp = self.client.get(reverse("lessons:index"))
        self.assertContains(resp, reverse("lessons:polite"))
        self.assertEqual(resp.context["active_nav"], "lessons")
